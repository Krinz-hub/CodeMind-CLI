"""Bounded multi-turn execution loop for CodeMind CLI.

Provides resilient turn-budgeting, cancellation safety, task pause preservation,
and structured progress tracking.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from codemind.cli.ui import TerminalUI
from codemind.context.compactor import ContextCompactor
from codemind.models.base import ChatMessage, ModelAdapter, ModelError
from codemind.models.protocol import (
    ActionType,
    FinalAction,
    MalformedAction,
    ParsedAction,
    PlanAction,
    ProtocolParser,
    ToolCallAction,
)
from codemind.planning.planner import Planner
from codemind.planning.task import TaskStatus
from codemind.runtime.events import AgentEvent, AgentEventType, EventListener
from codemind.runtime.state import AgentState
from codemind.tools.base import ExecutionContext, ToolResult
from codemind.tools.registry import ToolRegistry


class AgentLoop:
    """Manages bounded iterative turns between model reasoning and tool execution."""

    def __init__(
        self,
        model_adapter: ModelAdapter,
        tool_registry: ToolRegistry,
        execution_context: ExecutionContext,
        planner: Planner,
        max_turns: int = 20,
        max_tool_calls: int = 30,
        ui: TerminalUI | None = None,
        event_listener: EventListener | None = None,
        compactor: ContextCompactor | None = None,
    ):
        self.model = model_adapter
        self.tools = tool_registry
        self.context = execution_context
        self.planner = planner
        self.max_turns = max_turns
        self.max_tool_calls = max_tool_calls
        self.ui = ui
        self.event_listener = event_listener
        self._cancelled = False
        self.compactor = compactor or ContextCompactor(
            threshold_chars=min(40000, max(8000, getattr(self.model.capability_profile, "context_window", 32768) * 3))
        )

    def cancel(self) -> None:
        """Signal the loop to stop immediately on next yield."""
        self._cancelled = True

    def _emit(self, event_type: AgentEventType, session_id: str, data: dict[str, Any]) -> None:
        if self.event_listener:
            ev = AgentEvent(event_type=event_type, session_id=session_id, data=data)
            self.event_listener(ev)

    def _pause_running_tasks(self, state: AgentState, reason: str = "Turn limit reached") -> None:
        """Mark active in-progress tasks in the plan as paused."""
        if state.plan and state.plan.tasks:
            for t in state.plan.tasks:
                if t.status in (TaskStatus.RUNNING, TaskStatus.IN_PROGRESS):
                    t.mark_status(TaskStatus.PAUSED, evidence=reason)

    async def execute_task(self, state: AgentState) -> AgentState:
        """Run the bounded loop until final completion, turn limit, pause, or error."""
        consecutive_malformed = 0
        max_malformed_retries = 3

        while state.turn_count < self.max_turns and not state.is_complete and not self._cancelled:
            # Check user cancellation
            if self._cancelled:
                break

            state.turn_count += 1
            self._emit(
                AgentEventType.TURN_START,
                state.session_id,
                {"turn": state.turn_count, "tool_calls": state.total_tool_calls, "max_turns": self.max_turns},
            )

            # Check tool call ceiling
            if state.total_tool_calls >= self.max_tool_calls:
                msg = f"Task paused: Exceeded maximum allowed tool calls ({self.max_tool_calls})."
                if self.ui:
                    self.ui.print_error(msg)
                state.final_content = msg
                state.is_paused = True
                state.is_complete = False
                state.status = "paused"
                self._pause_running_tasks(state, "Exceeded tool call budget")
                self._emit(
                    AgentEventType.TASK_PAUSED,
                    state.session_id,
                    {"reason": "tool_limit", "total_tool_calls": state.total_tool_calls},
                )
                break

            # Check context compaction
            if self.compactor.needs_compaction(state.messages):
                comp_res = self.compactor.compact(
                    messages=state.messages,
                    task_plan=state.plan,
                )
                if comp_res.was_compacted:
                    state.messages = comp_res.messages
                    if self.ui:
                        self.ui.print_info(
                            f"Context compacted to conserve model window (saved {comp_res.saved_chars} characters)."
                        )

            # 1. Model generation
            self._emit(AgentEventType.MODEL_REQUEST, state.session_id, {"turn": state.turn_count})
            try:
                model_response = await self.model.generate(state.messages)
            except asyncio.CancelledError:
                self._cancelled = True
                break
            except ModelError as m_err:
                err_msg = f"Model serving error: {m_err}"
                if self.ui:
                    self.ui.print_error(err_msg)
                self._emit(AgentEventType.ERROR, state.session_id, {"error": str(m_err)})
                state.final_content = err_msg
                state.status = "failed"
                state.is_complete = False
                break
            except Exception as ex:
                err_msg = f"Unexpected model error: {ex}"
                if self.ui:
                    self.ui.print_error(err_msg)
                state.final_content = err_msg
                state.status = "failed"
                state.is_complete = False
                break

            raw_text = model_response.content
            self._emit(
                AgentEventType.MODEL_RESPONSE,
                state.session_id,
                {"raw_content": raw_text[:500]},
            )

            # 2. Protocol parsing
            action: ParsedAction = ProtocolParser.parse(raw_text)

            # 3. Action handling
            if isinstance(action, ToolCallAction):
                consecutive_malformed = 0
                state.total_tool_calls += 1

                # Update plan step to running if relevant
                if state.plan and state.plan.tasks:
                    for t in state.plan.tasks:
                        if t.status in (TaskStatus.PENDING, TaskStatus.READY) and not any(
                            other.status == TaskStatus.RUNNING for other in state.plan.tasks
                        ):
                            t.mark_status(TaskStatus.RUNNING)
                            break

                if self.ui:
                    self.ui.print_tool_call(action.tool, action.reason, action.arguments)

                self._emit(
                    AgentEventType.TOOL_START,
                    state.session_id,
                    {"tool": action.tool, "arguments": action.arguments, "reason": action.reason},
                )

                # Execute tool
                tool_res: ToolResult = await self.tools.execute(
                    action.tool,
                    action.arguments,
                    self.context,
                )

                if self.ui:
                    self.ui.print_tool_result(tool_res.ok, tool_res.content, tool_res.truncated)

                self._emit(
                    AgentEventType.TOOL_END,
                    state.session_id,
                    {"tool": action.tool, "ok": tool_res.ok, "exit_code": tool_res.exit_code},
                )

                # Track file changes
                if tool_res.ok and tool_res.metadata:
                    if "path" in tool_res.metadata:
                        state.record_file_created(tool_res.metadata["path"])
                    if "file" in tool_res.metadata:
                        state.record_file_modified(tool_res.metadata["file"])

                # Record messages into conversation
                state.add_message("assistant", raw_text)

                obs_payload = {
                    "tool": action.tool,
                    "ok": tool_res.ok,
                    "output": tool_res.content,
                    "exit_code": tool_res.exit_code,
                    "truncated": tool_res.truncated,
                }
                state.add_message("user", f"Tool Observation:\n{json.dumps(obs_payload, indent=2)}")

            elif isinstance(action, PlanAction):
                consecutive_malformed = 0
                self.planner.update_from_model_action(action)
                state.plan = self.planner.plan

                if self.ui:
                    self.ui.print_plan(state.plan.to_dict_list())

                self._emit(
                    AgentEventType.PLAN_UPDATED,
                    state.session_id,
                    {"plan": state.plan.to_dict_list(), "reason": action.reason},
                )

                state.add_message("assistant", raw_text)
                state.add_message(
                    "user",
                    f"Plan received and recorded. Active plan status:\n{state.plan.format_text()}.\nProceed with next step.",
                )

            elif isinstance(action, FinalAction):
                consecutive_malformed = 0
                state.is_complete = True
                state.is_paused = False
                state.status = "completed"
                state.final_content = action.content
                state.final_summary = action.summary

                # Mark all remaining running tasks as completed
                if state.plan and state.plan.tasks:
                    for t in state.plan.tasks:
                        if t.status in (TaskStatus.RUNNING, TaskStatus.IN_PROGRESS):
                            t.mark_status(TaskStatus.COMPLETED, evidence="Action 'final' received")

                state.add_message("assistant", raw_text)
                self._emit(
                    AgentEventType.TASK_COMPLETED,
                    state.session_id,
                    {"summary": action.summary, "content": action.content[:500]},
                )
                break

            elif isinstance(action, MalformedAction):
                consecutive_malformed += 1
                # Invariant: Protocol repair attempts use a dedicated retry sub-budget
                # and do NOT burn through the user's primary execution turn budget.
                state.turn_count = max(0, state.turn_count - 1)
                if self.ui:
                    self.ui.print_error(
                        f"Malformed model response ({action.validation_error}) [Repair attempt {consecutive_malformed}/{max_malformed_retries}]"
                    )

                if consecutive_malformed >= max_malformed_retries:
                    abort_msg = (
                        f"Aborted: Model failed to emit valid protocol v1 envelope after {max_malformed_retries} attempts. "
                        f"Last error: {action.validation_error}"
                    )
                    state.final_content = abort_msg
                    state.is_complete = False
                    state.status = "failed"
                    state.is_paused = False
                    self._pause_running_tasks(state, f"Malformed envelope failure: {action.validation_error}")
                    break

                # Send feedback loopback
                state.add_message("assistant", action.raw_content)
                state.add_message("user", f"Validation Error: {action.correction_prompt}")

        # Post-loop state resolution
        if self._cancelled:
            state.is_cancelled = True
            state.is_paused = True
            state.is_complete = False
            state.status = "cancelled"
            state.final_content = "Task cancelled by user. State and checkpoint preserved."
            self._pause_running_tasks(state, "Cancelled by user")
            self._emit(AgentEventType.TASK_CANCELLED, state.session_id, {"turn": state.turn_count})
            if self.ui:
                self.ui.print_warning(state.final_content)

        elif not state.is_complete and state.turn_count >= self.max_turns:
            state.is_paused = True
            state.is_complete = False
            state.status = "paused"
            state.final_content = f"Turn limit reached ({self.max_turns} turns). Task has been paused."
            self._pause_running_tasks(state, "Turn limit reached")
            self._emit(
                AgentEventType.TASK_PAUSED,
                state.session_id,
                {"turn": state.turn_count, "max_turns": self.max_turns},
            )
            if self.ui:
                self.ui.print_warning(f"\n⏸ Task Paused: Turn limit reached ({self.max_turns}/{self.max_turns} turns).")
                self.ui.print_info("Type 'continue' to resume this task with a fresh turn budget, or enter a new request.")

        return state
