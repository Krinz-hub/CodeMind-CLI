"""High-level CodeMindAgent orchestrating models, tools, context, verification, and checkpoints."""

from __future__ import annotations

import asyncio
import datetime
import os
import uuid
from pathlib import Path

from codemind.cli.ui import TerminalUI
from codemind.config import CodeMindConfig
from codemind.connectors.manager import ConnectorManager
from codemind.context.budget import ContextBudget
from codemind.context.discovery import ProjectDiscovery, ProjectSummary
from codemind.mcp.manager import MCPManager
from codemind.memory.distiller import MemoryDistiller
from codemind.memory.retriever import MemoryRetriever
from codemind.memory.store import SQLiteProjectMemory
from codemind.models import create_adapter
from codemind.models.base import ChatMessage, ModelAdapter
from codemind.orchestration.checkpoint import CheckpointManager, WorkflowCheckpoint
from codemind.planning.planner import Planner
from codemind.planning.task import TaskPlan, TaskStatus
from codemind.runtime.events import AgentEvent, AgentEventType
from codemind.runtime.loop import AgentLoop
from codemind.runtime.state import AgentState
from codemind.security.permissions import PermissionChecker
from codemind.security.sandbox import WorkspaceSandbox
from codemind.sessions.manager import SessionManager
from codemind.sessions.store import SessionSnapshot
from codemind.skills.loader import SkillLoader
from codemind.skills.registry import SkillRegistry
from codemind.tools.base import ExecutionContext
from codemind.tools.registry import ToolRegistry
from codemind.verification.reporter import HonestCompletionReport
from codemind.verification.runner import VerificationRunner

DEFAULT_SYSTEM_INSTRUCTIONS = (
    "You are Milo, the local AI engineering companion powered by CodeMind.\n"
    "Your purpose is to assist developers with real software engineering work:\n"
    "reading code, planning changes, editing files safely, running tests, and verifying outcomes.\n\n"
    "OPERATING RULES:\n"
    "1. Always inspect relevant files before modifying anything.\n"
    "2. For multi-step tasks, propose a structured plan first using action type 'plan'.\n"
    "3. Use targeted edits via 'apply_patch' or 'create_file'. Avoid full rewrites when possible.\n"
    "4. Never hallucinate test results or claim something works without verification.\n"
    "5. Emit strictly valid JSON matching the v1 protocol envelope.\n"
)


class CodeMindAgent:
    """Autonomous local agent runtime orchestrator with checkpoint and session isolation."""

    def __init__(self, config: CodeMindConfig, ui: TerminalUI | None = None):
        self.config = config
        self.ui = ui or TerminalUI(plain_mode=config.plain_mode)
        self.workspace_root = Path(config.workspace_root).resolve()

        # Core components
        self.sandbox = WorkspaceSandbox(
            self.workspace_root,
            allow_external=config.security.allow_external_paths,
        )
        self.permission_checker = PermissionChecker(
            mode=config.security.permission_mode,
            workspace_root=self.workspace_root,
        )
        self.tools = ToolRegistry()
        self.mcp = MCPManager(self.workspace_root)
        self.connectors = ConnectorManager(self.workspace_root)
        self.model: ModelAdapter = create_adapter(config.model)
        self.discovery = ProjectDiscovery(self.workspace_root)
        self.budget = ContextBudget()
        self.sessions = SessionManager(self.workspace_root)
        self.verification = VerificationRunner(self.workspace_root, self.sandbox)
        self.skills = SkillRegistry(self.workspace_root)
        self.skill_loader = SkillLoader(self.workspace_root)
        self.memory = SQLiteProjectMemory(self.workspace_root)
        self.retriever = MemoryRetriever(self.memory)
        self.distiller = MemoryDistiller(self.memory)
        self.checkpoint_manager = CheckpointManager(self.workspace_root)

        self.active_snapshot: SessionSnapshot | None = None
        self.active_checkpoint: WorkflowCheckpoint | None = None
        self.active_task_id: str | None = None
        self.active_state: AgentState | None = None
        self._current_loop: AgentLoop | None = None

    async def initialize(self, resume_session_id: str | None = None) -> None:
        """Initialize session and recover prior state if resuming."""
        if resume_session_id:
            loaded = self.sessions.load_session(resume_session_id)
            if loaded:
                self.active_snapshot = loaded
                self.active_checkpoint = self.checkpoint_manager.load_latest_checkpoint(resume_session_id)
                self.ui.print_info(f"Resumed session '{loaded.session_id}' ({loaded.turns_completed} prior turns).")
                return
            else:
                self.ui.print_error(f"Could not find saved session matching '{resume_session_id}'. Starting fresh.")

        self.active_snapshot = SessionSnapshot(
            workspace_root=str(self.workspace_root),
            model_name=self.config.model.model_name,
            provider=self.config.model.provider.value,
            permission_mode=self.config.security.permission_mode.value,
        )

        # Discover and register active MCP tools
        try:
            mcp_tools = await self.mcp.initialize_servers(self.tools)
            if mcp_tools:
                self.ui.print_info(f"Initialized {len(mcp_tools)} tool(s) from local MCP server(s).")
        except Exception:
            pass

        # Discover and register active connected application tools
        try:
            conn_tools_cnt = self.connectors.register_tools_with(self.tools)
            if conn_tools_cnt:
                self.ui.print_info(f"Initialized {conn_tools_cnt} tool(s) from connected application(s).")
        except Exception:
            pass

    async def shutdown(self) -> None:
        """Cleanly close all background MCP servers and subprocesses."""
        await self.mcp.shutdown_all()

    def cancel_active_task(self) -> None:
        """Signal cancellation to currently executing task loop."""
        if self._current_loop:
            self._current_loop.cancel()

    def _event_handler(self, event: AgentEvent) -> None:
        """Log event to session trace."""
        if self.active_snapshot:
            self.sessions.append_event(
                self.active_snapshot.session_id,
                event.event_type.value,
                event.data,
            )

    async def resume_paused_task(self, max_turns: int | None = None) -> AgentState:
        """Resume execution of the currently paused task with a fresh turn budget."""
        has_paused_task = (
            (self.active_state and self.active_state.is_paused)
            or (self.active_snapshot and not self.active_snapshot.is_completed)
            or (self.active_checkpoint and not self.active_checkpoint.is_completed)
        )
        if not self.active_snapshot or not has_paused_task:
            self.ui.print_error("No paused task available to resume in this session.")
            state = AgentState(
                session_id=self.active_snapshot.session_id if self.active_snapshot else "unknown",
                workspace_root=str(self.workspace_root),
                final_content="No paused task found to resume.",
            )
            return state

        # Find the last instruction or generate continuation prompt
        instruction = "Continue previous task"
        if self.active_checkpoint and self.active_checkpoint.instruction:
            instruction = self.active_checkpoint.instruction
        elif self.active_state and self.active_state.task_instruction:
            instruction = self.active_state.task_instruction

        self.ui.print_info(f"Continuing paused task: '{instruction}'")
        return await self.run_task(instruction=instruction, is_continuation=True, max_turns=max_turns)

    async def run_task(
        self,
        instruction: str,
        is_continuation: bool = False,
        max_turns: int | None = None,
    ) -> AgentState:
        """Execute a complete task instruction with strict session isolation and budget guarantees."""
        if not self.active_snapshot:
            await self.initialize()

        assert self.active_snapshot is not None

        # 1. Project discovery
        project_summary: ProjectSummary = self.discovery.analyze()

        # 2. Retrieve persistent project memory
        memory_text = self.retriever.retrieve_context(
            instruction=instruction,
            project_summary=project_summary,
        )

        # 3. Intelligent Skill Selection (grounded by manifests and project memory)
        skill_selection = self.skills.select_skills(
            instruction=instruction,
            manifest_files=project_summary.manifest_files,
            project_type=project_summary.project_type,
            memory_context=memory_text,
        )
        skills_text = None
        if skill_selection.selected_skills:
            skill_names = [s.name for s in skill_selection.selected_skills]
            self.ui.print_info(f"Active skill(s): {', '.join(skill_names)}")
            skills_text = self.skills.format_skills_for_prompt(skill_selection.selected_skills)

        # 4. Task Plan initialization
        planner = Planner()
        if is_continuation and self.active_snapshot.plan:
            for p in self.active_snapshot.plan:
                status_str = p.get("status", "pending")
                # Any task left paused becomes ready/running on continuation
                if status_str == "paused":
                    status_str = "pending"
                planner.plan.add_or_update(
                    task_id=p.get("id", ""),
                    title=p.get("title", ""),
                    status=status_str,
                    notes=p.get("notes", ""),
                )
        elif not is_continuation:
            # Clean task plan for new task
            pass

        # 5. Unique Task ID for this specific task
        if is_continuation and self.active_task_id:
            task_id = self.active_task_id
        else:
            task_id = f"task-{datetime.datetime.now().strftime('%H%M%S')}-{uuid.uuid4().hex[:6]}"
            self.active_task_id = task_id

        # 6. Assemble system prompt
        tool_defs = self.tools.get_prompt_definitions()
        system_prompt = self.budget.assemble_system_prompt(
            base_instructions=DEFAULT_SYSTEM_INSTRUCTIONS,
            tool_definitions=tool_defs,
            project_summary=project_summary,
            active_plan_text=planner.plan.format_text() if planner.plan.tasks else None,
            skills_text=skills_text,
            memory_text=memory_text if memory_text else None,
        )

        # 7. Build state & messages
        messages: list[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]
        if is_continuation:
            # Re-inject prior conversation history when continuing
            for h in self.active_snapshot.history:
                messages.append(ChatMessage(role=h["role"], content=h["content"]))
            plan_str = f" in the plan: {planner.plan.format_text()}" if planner.plan.tasks else " to complete the task"
            continuation_directive = (
                f"Resuming task after turn-budget pause. Previous completed tasks are preserved. "
                f"Proceed immediately with remaining pending tasks{plan_str}."
            )
            messages.append(ChatMessage(role="user", content=continuation_directive))
        else:
            messages.append(ChatMessage(role="user", content=instruction))

        # IMPORTANT: Fresh segment budget starting at turn_count = 0
        # Restore task-specific file mutations strictly for continuation of this exact task, never from global history
        restored_created: list[str] = []
        restored_modified: list[str] = []
        if is_continuation and self.active_checkpoint and getattr(self.active_checkpoint, "current_task_id", None) == task_id:
            restored_created = list(self.active_checkpoint.files_created)
            restored_modified = list(self.active_checkpoint.files_modified)

        state = AgentState(
            session_id=self.active_snapshot.session_id,
            workspace_root=str(self.workspace_root),
            task_instruction=instruction,
            current_task_id=task_id,
            turn_count=0,
            files_created=restored_created,
            files_modified=restored_modified,
            messages=messages,
            plan=planner.plan,
        )
        self.active_state = state

        # 8. Setup execution context
        exec_context = ExecutionContext(
            workspace_root=self.workspace_root,
            sandbox=self.sandbox,
            permission_checker=self.permission_checker,
            max_output_bytes=self.config.runtime.max_output_bytes,
            timeout_seconds=self.config.runtime.tool_timeout_seconds,
            ui=self.ui,
        )

        # 9. Configure turn budget
        task_budget = max_turns or self.config.runtime.max_turns

        # 10. Run bounded loop with cancellation protection
        loop = AgentLoop(
            model_adapter=self.model,
            tool_registry=self.tools,
            execution_context=exec_context,
            planner=planner,
            max_turns=task_budget,
            max_tool_calls=self.config.runtime.max_tool_calls,
            ui=self.ui,
            event_listener=self._event_handler,
        )
        self._current_loop = loop

        try:
            final_state = await loop.execute_task(state)
        except (asyncio.CancelledError, KeyboardInterrupt):
            state.is_cancelled = True
            state.is_paused = True
            state.is_complete = False
            state.status = "cancelled"
            state.final_content = "Task interrupted by user (Ctrl+C). Checkpoint preserved."
            final_state = state
            self.ui.print_warning("\nSession interrupted. Task paused and safely checkpointed.")
        finally:
            self._current_loop = None

        # 11. Rigorous, honest completion report (task-specific, no stale leaks)
        report = HonestCompletionReport(
            task_id=task_id,
            task_instruction=instruction,
            files_created=final_state.files_created,
            files_modified=final_state.files_modified,
            task_completed=final_state.is_complete,
            is_paused=final_state.is_paused,
            is_cancelled=final_state.is_cancelled,
        )

        has_modifications = bool(final_state.files_created or final_state.files_modified)

        # Run verification checks ONLY if task actually finished without pausing or cancelling
        if has_modifications and final_state.is_complete and self.config.runtime.auto_verify:
            changed_files = list(set(final_state.files_created + final_state.files_modified))
            test_cmd = self.verification.discover_test_command(changed_files=changed_files)
            if test_cmd:
                self.ui.print_info(f"Running verification suite: '{test_cmd}'...")
                check_result = await self.verification.run_check(test_cmd)
                report.checks.append(check_result)
            else:
                report.unverified_notes.append("No automated test runner discovered for this project.")
        elif final_state.is_paused:
            report.unverified_notes.append("Task paused at turn limit; verification withheld until task is completed.")
        elif final_state.is_cancelled:
            report.unverified_notes.append("Task cancelled before verification could be performed.")

        # 12. Render final response and verification card
        if final_state.final_content:
            self.ui.print_final_response(
                content=final_state.final_content,
                summary=final_state.final_summary,
            )

        if has_modifications or not final_state.is_complete:
            self.ui.print_verification_card(report, self.workspace_root)

        # 13. Persist atomic workflow checkpoint
        completed_ids = [
            t.id for t in final_state.plan.tasks if t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
        ]
        pending_ids = [
            t.id
            for t in final_state.plan.tasks
            if t.status in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.PAUSED)
        ]
        failed_ids = [t.id for t in final_state.plan.tasks if t.status == TaskStatus.FAILED]

        ckpt = WorkflowCheckpoint(
            session_id=self.active_snapshot.session_id,
            workspace_root=str(self.workspace_root),
            instruction=instruction,
            current_task_id=task_id,
            tasks=final_state.plan.to_dict_list(),
            completed_task_ids=completed_ids,
            pending_task_ids=pending_ids,
            failed_task_ids=failed_ids,
            files_created=final_state.files_created,
            files_modified=final_state.files_modified,
            total_turns=self.active_snapshot.turns_completed + final_state.turn_count,
            total_tool_calls=final_state.total_tool_calls,
            is_completed=final_state.is_complete,
        )
        self.checkpoint_manager.save_checkpoint_atomic(ckpt)
        self.active_checkpoint = ckpt

        # 14. Persist session snapshot
        self.active_snapshot.turns_completed += final_state.turn_count
        self.active_snapshot.plan = final_state.plan.to_dict_list()
        if final_state.is_complete:
            self.active_snapshot.files_changed = list(
                set(self.active_snapshot.files_changed + final_state.files_created + final_state.files_modified)
            )
            self.active_snapshot.is_completed = True
        else:
            self.active_snapshot.is_completed = False

        self.active_snapshot.history = [
            {"role": m.role, "content": m.content} for m in final_state.messages if m.role != "system"
        ]
        self.sessions.save_checkpoint(self.active_snapshot)
        self.ui.print_info(f"Session state saved: {self.active_snapshot.session_id}")

        # 15. Distill memories ONLY from tasks that completed cleanly without pause or cancellation
        if final_state.is_complete and not final_state.is_paused and not final_state.is_cancelled:
            created_memories = self.distiller.distill(
                state=final_state,
                report=report,
                project_summary=project_summary,
            )
            if created_memories:
                self.ui.print_info(f"Distilled {len(created_memories)} memory record(s) into persistent store.")

        return final_state
