"""Bounded multi-turn execution loop for CodeMind CLI."""

from __future__ import annotations

import json
from typing import Any, Callable

from codemind.cli.ui import TerminalUI
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
    ):
        self.model = model_adapter
        self.tools = tool_registry
        self.context = execution_context
        self.planner = planner
        self.max_turns = max_turns
        self.max_tool_calls = max_tool_calls
        self.ui = ui
        self.event_listener = event_listener

    def _emit(self, event_type: AgentEventType, session_id: str, data: dict[str, Any]) -> None:
        if self.event_listener:
            ev = AgentEvent(event_type=event_type, session_id=session_id, data=data)
            self.event_listener(ev)

    async def execute_task(self, state: AgentState) -> AgentState:
        """Run the bounded loop until final completion, turn limit, or error."""
        consecutive_malformed = 0
        max_malformed_retries = 3

        while state.turn_count < self.max_turns and not state.is_complete:
            state.turn_count += 1
            self._emit(
                AgentEventType.TURN_START,
                state.session_id,
                {"turn": state.turn_count, "tool_calls": state.total_tool_calls},
            )

            # Check tool call ceiling
            if state.total_tool_calls >= self.max_tool_calls:
                msg = f"Task aborted: Exceeded maximum allowed tool calls ({self.max_tool_calls})."
                if self.ui:
                    self.ui.print_error(msg)
                state.final_content = msg
                state.is_complete = True
                break

            # 1. Model generation
            self._emit(AgentEventType.MODEL_REQUEST, state.session_id, {"turn": state.turn_count})
            try:
                model_response = await self.model.generate(state.messages)
            except ModelError as m_err:
                err_msg = f"Model serving error: {m_err}"
                if self.ui:
                    self.ui.print_error(err_msg)
                self._emit(AgentEventType.ERROR, state.session_id, {"error": str(m_err)})
                state.final_content = err_msg
                break
            except Exception as ex:
                err_msg = f"Unexpected model error: {ex}"
                if self.ui:
                    self.ui.print_error(err_msg)
                state.final_content = err_msg
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
                state.final_content = action.content
                state.final_summary = action.summary

                state.add_message("assistant", raw_text)
                self._emit(
                    AgentEventType.TASK_COMPLETED,
                    state.session_id,
                    {"summary": action.summary, "content": action.content[:500]},
                )
                break

            elif isinstance(action, MalformedAction):
                consecutive_malformed += 1
                if self.ui:
                    self.ui.print_error(f"Malformed model response ({action.validation_error})")

                if consecutive_malformed >= max_malformed_retries:
                    abort_msg = (
                        f"Aborted: Model failed to emit valid protocol v1 envelope after {max_malformed_retries} attempts. "
                        f"Last error: {action.validation_error}"
                    )
                    state.final_content = abort_msg
                    state.is_complete = True
                    break

                # Send feedback loopback
                state.add_message("assistant", action.raw_content)
                state.add_message("user", f"Validation Error: {action.correction_prompt}")

        if not state.is_complete and state.turn_count >= self.max_turns:
            state.final_content = f"Turn limit reached ({self.max_turns} turns). Task paused."
            if self.ui:
                self.ui.print_error(state.final_content)

        return state
