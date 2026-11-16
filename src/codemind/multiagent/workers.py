"""Specialized worker agent implementations: Research, Coding, Debugging, Testing."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from codemind.cli.ui import TerminalUI
from codemind.config import CodeMindConfig, PermissionMode
from codemind.models.base import ModelAdapter
from codemind.multiagent.models import (
    AgentRole,
    ChangeProposal,
    InterAgentMessage,
    MessageType,
    WorkerConfig,
    WorkerStatus,
)
from codemind.multiagent.workspace import WorkerWorkspaceManager
from codemind.runtime.agent import CodeMindAgent
from codemind.runtime.state import AgentState


class WorkerAgent:
    """Base specialized worker agent executing within an isolated sandbox."""

    def __init__(
        self,
        config: WorkerConfig,
        global_config: CodeMindConfig,
        workspace_manager: WorkerWorkspaceManager,
        custom_model: ModelAdapter | None = None,
        ui: TerminalUI | None = None,
    ):
        self.config = config
        self.global_config = global_config
        self.workspace_manager = workspace_manager
        self.status = WorkerStatus.IDLE
        self.workspace_path = Path(config.workspace_path).resolve()
        self.assigned_task_id: str | None = None
        self.event_log: list[str] = []
        self.ui = ui

        # Create worker-specific configuration pointing strictly to isolated workspace
        perm_mode = PermissionMode.READ_ONLY if config.read_only else PermissionMode.TRUSTED
        self.agent_config = CodeMindConfig(
            workspace_root=str(self.workspace_path),
            plain_mode=True,
            model=global_config.model,
            security={"permission_mode": perm_mode, "allow_external_paths": False},
            runtime={"max_turns": config.max_turns},
        )
        self.agent = CodeMindAgent(self.agent_config, ui=self.ui)
        if custom_model:
            self.agent.model = custom_model

    def log(self, message: str) -> None:
        """Record an event into worker audit log."""
        self.event_log.append(message)

    async def initialize(self) -> None:
        """Initialize agent runtime inside isolated workspace."""
        await self.agent.initialize()
        self.status = WorkerStatus.IDLE

    async def execute_task_assignment(self, message: InterAgentMessage) -> InterAgentMessage:
        """Execute assigned task and return structured completion or findings message."""
        self.assigned_task_id = message.task_id
        self.status = WorkerStatus.RUNNING
        task_instruction = message.payload.get("instruction", "")
        self.log(f"Received task {message.task_id}: {task_instruction[:60]}")

        # Assemble prompt with role-specific constraints and memory summaries
        role_prompt = self._build_role_prompt(task_instruction, message.payload)

        try:
            state: AgentState = await self.agent.run_task(role_prompt)
            if not state.is_complete:
                self.status = WorkerStatus.FAILED
                err_msg = state.final_content or "Worker task failed or was incomplete"
                self.log(f"Task {message.task_id} failed: {err_msg}")
                return InterAgentMessage(
                    task_id=message.task_id,
                    sender_agent=self.config.worker_id,
                    recipient="coordinator",
                    message_type=MessageType.FAILURE,
                    correlation_id=message.message_id,
                    payload={"error": err_msg, "worker_id": self.config.worker_id},
                )

            self.status = WorkerStatus.COMPLETED

            # Build result message based on role
            result_msg = self._build_result_message(message, state)
            self.log(f"Completed task {message.task_id} with status {result_msg.message_type.value}")
            return result_msg

        except Exception as ex:
            self.status = WorkerStatus.FAILED
            self.log(f"Task {message.task_id} failed: {ex}")
            return InterAgentMessage(
                task_id=message.task_id,
                sender_agent=self.config.worker_id,
                recipient="coordinator",
                message_type=MessageType.FAILURE,
                correlation_id=message.message_id,
                payload={"error": str(ex), "worker_id": self.config.worker_id},
            )

    def _build_role_prompt(self, instruction: str, payload: dict[str, Any]) -> str:
        """Construct specialized system/task prompt for the assigned role."""
        return instruction

    def _build_result_message(self, assignment: InterAgentMessage, state: AgentState) -> InterAgentMessage:
        """Construct structured return message based on role output."""
        return InterAgentMessage(
            task_id=assignment.task_id,
            sender_agent=self.config.worker_id,
            recipient="coordinator",
            message_type=MessageType.TASK_COMPLETED,
            correlation_id=assignment.message_id,
            payload={"summary": state.final_content or "Completed."},
        )


class ResearchWorker(WorkerAgent):
    """Specialized read-only worker for repository reconnaissance and architecture analysis."""

    def __init__(
        self,
        config: WorkerConfig,
        global_config: CodeMindConfig,
        workspace_manager: WorkerWorkspaceManager,
        custom_model: ModelAdapter | None = None,
        ui: TerminalUI | None = None,
    ):
        super().__init__(config, global_config, workspace_manager, custom_model=custom_model, ui=ui)

    def _build_role_prompt(self, instruction: str, payload: dict[str, Any]) -> str:
        return (
            "ROLE: Research Agent (Read-Only Reconnaissance)\n"
            "Analyze the project structure, dependencies, and important components.\n"
            "Do NOT modify or create files.\n\n"
            f"ASSIGNMENT: {instruction}\n"
        )

    def _build_result_message(self, assignment: InterAgentMessage, state: AgentState) -> InterAgentMessage:
        return InterAgentMessage(
            task_id=assignment.task_id,
            sender_agent=self.config.worker_id,
            recipient="coordinator",
            message_type=MessageType.FINDINGS,
            correlation_id=assignment.message_id,
            payload={
                "findings": state.final_content or "Reconnaissance complete.",
                "files_inspected": state.files_created,  # In read-only, track files read
            },
        )


class CodingWorker(WorkerAgent):
    """Specialized worker for implementing features and producing change proposals."""

    def __init__(
        self,
        config: WorkerConfig,
        global_config: CodeMindConfig,
        workspace_manager: WorkerWorkspaceManager,
        custom_model: ModelAdapter | None = None,
        ui: TerminalUI | None = None,
    ):
        super().__init__(config, global_config, workspace_manager, custom_model=custom_model, ui=ui)

    def _build_role_prompt(self, instruction: str, payload: dict[str, Any]) -> str:
        mem = payload.get("memory_context", "")
        skills = ", ".join(self.config.assigned_skills)
        prompt = (
            f"ROLE: Coding Agent (Feature Implementation)\n"
            f"Active Skills: {skills or 'General Software Engineering'}\n"
        )
        if mem:
            prompt += f"Project Decisions & Rules: {mem}\n"
        prompt += f"\nASSIGNMENT: {instruction}\nImplement cleanly and ensure all files are created or edited properly.\n"
        return prompt

    def _build_result_message(self, assignment: InterAgentMessage, state: AgentState) -> InterAgentMessage:
        # Extract change proposal diffs from isolated workspace
        proposal: ChangeProposal = self.workspace_manager.extract_change_proposal(
            self.config.worker_id,
            assignment.task_id,
        )
        return InterAgentMessage(
            task_id=assignment.task_id,
            sender_agent=self.config.worker_id,
            recipient="coordinator",
            message_type=MessageType.CHANGE_PROPOSAL,
            correlation_id=assignment.message_id,
            payload={
                "proposal": proposal.model_dump(),
                "summary": state.final_content or proposal.summary,
            },
        )


class DebuggingWorker(WorkerAgent):
    """Specialized worker for analyzing failures, isolating root causes, and applying fixes."""

    def __init__(
        self,
        config: WorkerConfig,
        global_config: CodeMindConfig,
        workspace_manager: WorkerWorkspaceManager,
        custom_model: ModelAdapter | None = None,
        ui: TerminalUI | None = None,
    ):
        super().__init__(config, global_config, workspace_manager, custom_model=custom_model, ui=ui)

    def _build_role_prompt(self, instruction: str, payload: dict[str, Any]) -> str:
        error_context = payload.get("error_context", "")
        return (
            "ROLE: Debugging Agent (Root-Cause Isolation & Repair)\n"
            f"Observed Error:\n{error_context}\n\n"
            f"ASSIGNMENT: {instruction}\n"
            "Isolate the root cause, apply minimal targeted fix, and verify resolution.\n"
        )

    def _build_result_message(self, assignment: InterAgentMessage, state: AgentState) -> InterAgentMessage:
        proposal = self.workspace_manager.extract_change_proposal(
            self.config.worker_id,
            assignment.task_id,
        )
        return InterAgentMessage(
            task_id=assignment.task_id,
            sender_agent=self.config.worker_id,
            recipient="coordinator",
            message_type=MessageType.CHANGE_PROPOSAL,
            correlation_id=assignment.message_id,
            payload={
                "proposal": proposal.model_dump(),
                "repair_summary": state.final_content or "Bug repaired.",
            },
        )


class TestingWorker(WorkerAgent):
    """Specialized worker for generating and running automated test suites."""

    def __init__(
        self,
        config: WorkerConfig,
        global_config: CodeMindConfig,
        workspace_manager: WorkerWorkspaceManager,
        custom_model: ModelAdapter | None = None,
        ui: TerminalUI | None = None,
    ):
        super().__init__(config, global_config, workspace_manager, custom_model=custom_model, ui=ui)

    def _build_role_prompt(self, instruction: str, payload: dict[str, Any]) -> str:
        return (
            "ROLE: Testing Agent (Test Suite Design & Verification)\n"
            "Follow the Arrange-Act-Assert (AAA) pattern and cover edge cases.\n\n"
            f"ASSIGNMENT: {instruction}\n"
            "Run unittest or pytest and verify that all test cases execute.\n"
        )

    def _build_result_message(self, assignment: InterAgentMessage, state: AgentState) -> InterAgentMessage:
        proposal = self.workspace_manager.extract_change_proposal(
            self.config.worker_id,
            assignment.task_id,
        )
        return InterAgentMessage(
            task_id=assignment.task_id,
            sender_agent=self.config.worker_id,
            recipient="coordinator",
            message_type=MessageType.REVIEW_REQUEST,
            correlation_id=assignment.message_id,
            payload={
                "proposal": proposal.model_dump(),
                "test_evidence": state.final_content or "Tests authored and executed.",
            },
        )
