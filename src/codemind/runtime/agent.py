"""High-level CodeMindAgent orchestrating models, tools, context, and verification."""

from __future__ import annotations

import os
from pathlib import Path

from codemind.cli.ui import TerminalUI
from codemind.config import CodeMindConfig
from codemind.context.budget import ContextBudget
from codemind.context.discovery import ProjectDiscovery, ProjectSummary
from codemind.models import create_adapter
from codemind.models.base import ChatMessage, ModelAdapter
from codemind.planning.planner import Planner
from codemind.planning.task import TaskPlan
from codemind.runtime.events import AgentEvent
from codemind.runtime.loop import AgentLoop
from codemind.runtime.state import AgentState
from codemind.security.permissions import PermissionChecker
from codemind.security.sandbox import WorkspaceSandbox
from codemind.sessions.manager import SessionManager
from codemind.sessions.store import SessionSnapshot
from codemind.skills.loader import SkillLoader
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
    """Autonomous local agent runtime orchestrator."""

    def __init__(self, config: CodeMindConfig, ui: TerminalUI | None = None):
        self.config = config
        self.ui = ui or TerminalUI(plain_mode=config.plain_mode)
        self.workspace_root = Path(config.workspace_root).resolve()

        # Core components
        self.sandbox = WorkspaceSandbox(
            self.workspace_root,
            allow_external=config.security.allow_external_paths,
        )
        self.permission_checker = PermissionChecker(mode=config.security.permission_mode)
        self.tools = ToolRegistry()
        self.model: ModelAdapter = create_adapter(config.model)
        self.discovery = ProjectDiscovery(self.workspace_root)
        self.budget = ContextBudget()
        self.sessions = SessionManager(self.workspace_root)
        self.verification = VerificationRunner(self.workspace_root, self.sandbox)
        self.skill_loader = SkillLoader(self.workspace_root)
        self.active_snapshot: SessionSnapshot | None = None

    async def initialize(self, resume_session_id: str | None = None) -> None:
        """Initialize session and recover prior state if resuming."""
        if resume_session_id:
            loaded = self.sessions.load_session(resume_session_id)
            if loaded:
                self.active_snapshot = loaded
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

    def _event_handler(self, event: AgentEvent) -> None:
        """Log event to session trace."""
        if self.active_snapshot:
            self.sessions.append_event(
                self.active_snapshot.session_id,
                event.event_type.value,
                event.data,
            )

    async def run_task(self, instruction: str) -> AgentState:
        """Execute a complete task instruction."""
        if not self.active_snapshot:
            await self.initialize()

        assert self.active_snapshot is not None

        # 1. Project discovery
        project_summary: ProjectSummary = self.discovery.analyze()

        # 2. Discover applicable skills
        applicable_skills = self.skill_loader.find_applicable_skills(
            project_summary.manifest_files,
            instruction,
        )
        skills_text = None
        if applicable_skills:
            skill_excerpts = [f"Skill: {s.name}\n{s.instructions}" for s in applicable_skills]
            skills_text = "\n\n".join(skill_excerpts)

        # 3. Restore existing plan if resuming, else fresh plan
        planner = Planner()
        if self.active_snapshot.plan:
            for p in self.active_snapshot.plan:
                planner.plan.add_or_update(
                    task_id=p.get("id", ""),
                    title=p.get("title", ""),
                    status=p.get("status", "pending"),
                    notes=p.get("notes", ""),
                )

        # 4. Assemble system prompt
        tool_defs = self.tools.get_prompt_definitions()
        system_prompt = self.budget.assemble_system_prompt(
            base_instructions=DEFAULT_SYSTEM_INSTRUCTIONS,
            tool_definitions=tool_defs,
            project_summary=project_summary,
            active_plan_text=planner.plan.format_text() if planner.plan.tasks else None,
            skills_text=skills_text,
        )

        # 5. Build state
        messages: list[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]
        # Re-inject prior conversation history if resuming
        for h in self.active_snapshot.history:
            messages.append(ChatMessage(role=h["role"], content=h["content"]))

        # Add new user instruction
        messages.append(ChatMessage(role="user", content=instruction))

        state = AgentState(
            session_id=self.active_snapshot.session_id,
            workspace_root=str(self.workspace_root),
            task_instruction=instruction,
            turn_count=self.active_snapshot.turns_completed,
            files_created=list(self.active_snapshot.files_changed),
            messages=messages,
            plan=planner.plan,
        )

        # 6. Setup execution context
        exec_context = ExecutionContext(
            workspace_root=self.workspace_root,
            sandbox=self.sandbox,
            permission_checker=self.permission_checker,
            max_output_bytes=self.config.runtime.max_output_bytes,
            timeout_seconds=self.config.runtime.tool_timeout_seconds,
            ui=self.ui,
        )

        # 7. Run bounded loop
        loop = AgentLoop(
            model_adapter=self.model,
            tool_registry=self.tools,
            execution_context=exec_context,
            planner=planner,
            max_turns=self.config.runtime.max_turns,
            max_tool_calls=self.config.runtime.max_tool_calls,
            ui=self.ui,
            event_listener=self._event_handler,
        )

        final_state = await loop.execute_task(state)

        # 8. Automated verification if files were modified/created and auto_verify is true
        report = HonestCompletionReport(
            files_created=final_state.files_created,
            files_modified=final_state.files_modified,
        )

        has_modifications = bool(final_state.files_created or final_state.files_modified)
        if has_modifications and self.config.runtime.auto_verify:
            test_cmd = self.verification.discover_test_command()
            if test_cmd:
                self.ui.print_info(f"Running verification suite: '{test_cmd}'...")
                check_result = await self.verification.run_check(test_cmd)
                report.checks.append(check_result)
                report.verified = check_result.passed
            else:
                report.unverified_notes.append("No automated test runner discovered for this project.")
                report.verified = False
        else:
            if not has_modifications:
                report.verified = True  # Read-only queries verified by nature of no mutation

        # 9. Render final response and honest completion report
        if final_state.final_content:
            self.ui.print_final_response(
                content=final_state.final_content,
                summary=final_state.final_summary,
            )

        if has_modifications:
            print(report.format_summary())

        # 10. Persist session snapshot
        self.active_snapshot.turns_completed = final_state.turn_count
        self.active_snapshot.plan = final_state.plan.to_dict_list()
        self.active_snapshot.files_changed = list(set(final_state.files_created + final_state.files_modified))
        self.active_snapshot.is_completed = final_state.is_complete
        self.active_snapshot.history = [
            {"role": m.role, "content": m.content}
            for m in final_state.messages
            if m.role != "system"
        ]
        self.sessions.save_checkpoint(self.active_snapshot)
        self.ui.print_info(f"Session saved: {self.active_snapshot.session_id}")

        return final_state
