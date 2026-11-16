"""Central Multi-Agent Coordinator governing task delegation, conflict resolution, and verification."""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from codemind.cli.ui import TerminalUI
from codemind.config import CodeMindConfig, PermissionMode
from codemind.context.discovery import ProjectDiscovery, ProjectSummary
from codemind.memory.distiller import MemoryDistiller
from codemind.memory.retriever import MemoryRetriever
from codemind.memory.store import SQLiteProjectMemory
from codemind.models.base import ModelAdapter
from codemind.multiagent.models import (
    AgentRole,
    ChangeProposal,
    InterAgentMessage,
    MessageType,
    MultiAgentConfig,
    WorkerConfig,
)
from codemind.multiagent.sidecar import SidecarRuntime
from codemind.multiagent.workers import (
    CodingWorker,
    DebuggingWorker,
    ResearchWorker,
    TestingWorker,
    WorkerAgent,
)
from codemind.multiagent.workspace import WorkerWorkspaceManager
from codemind.orchestration.models import CompletionStatus
from codemind.planning.task import (
    TaskComplexity,
    TaskItem,
    TaskPlan,
    TaskPriority,
    TaskStatus,
    VerificationCriterion,
)
from codemind.security.sandbox import WorkspaceSandbox
from codemind.skills.registry import SkillRegistry
from codemind.verification.reporter import HonestCompletionReport
from codemind.verification.runner import VerificationRunner


class MultiAgentCoordinator:
    """Supreme coordinator for multi-agent software engineering workflows."""

    def __init__(
        self,
        config: CodeMindConfig,
        multiagent_config: MultiAgentConfig | None = None,
        ui: TerminalUI | None = None,
        worker_model_factory: Callable[[AgentRole, str], ModelAdapter] | None = None,
    ):
        self.config = config
        self.ma_config = multiagent_config or MultiAgentConfig()
        self.ui = ui or TerminalUI(plain_mode=config.plain_mode)
        self.primary_root = Path(config.workspace_root).resolve()
        self.worker_model_factory = worker_model_factory

        # Shared Infrastructure
        self.discovery = ProjectDiscovery(self.primary_root)
        self.memory = SQLiteProjectMemory(self.primary_root)
        self.retriever = MemoryRetriever(self.memory)
        self.distiller = MemoryDistiller(self.memory)
        self.skills = SkillRegistry(self.primary_root)
        self.sandbox = WorkspaceSandbox(self.primary_root, allow_external=config.security.allow_external_paths)
        self.verification = VerificationRunner(self.primary_root, self.sandbox)
        self.workspace_manager = WorkerWorkspaceManager(self.primary_root)
        self.sidecar = SidecarRuntime(self.ma_config)

        # Plan & execution state
        self.plan = TaskPlan()
        self.assigned_roles: dict[str, AgentRole] = {}  # task_id -> AgentRole
        self.collected_findings: list[str] = []
        self.approved_proposals: list[ChangeProposal] = []
        self.total_inference_turns: int = 0
        self.total_tool_calls: int = 0

    def decompose_and_assign_roles(self, instruction: str) -> tuple[TaskPlan, dict[str, AgentRole]]:
        """Decompose instruction into a dependency DAG and assign specialized worker roles."""
        plan = TaskPlan()
        roles: dict[str, AgentRole] = {}
        inst_lower = instruction.lower()

        # Extract file paths from instruction
        paths_found = re.findall(r"[\w/\.-]+\.(?:py|js|ts|tsx|json|sql|html|css|md)", instruction)
        src_files = [p for p in paths_found if not any(t in p.lower() for t in ["test", "spec"])]
        test_files = [p for p in paths_found if any(t in p.lower() for t in ["test", "spec"])]

        # Check task characteristics
        is_bug_repair = any(w in inst_lower for w in ["fix", "bug", "repair", "debug", "failing", "error", "traceback"])
        is_research = any(w in inst_lower for w in ["research", "explore", "analyze", "investigate", "audit"])
        is_parallel_intent = "independent" in inst_lower or "parallel" in inst_lower or (len(src_files) > 1 and "both" in inst_lower)

        if is_parallel_intent and len(src_files) >= 2:
            # Independent parallel coding tasks
            for idx, sf in enumerate(src_files, 1):
                tid = f"task-{idx}"
                plan.add_or_update(
                    task_id=tid,
                    title=f"Implement component in {sf}",
                    status=TaskStatus.READY,
                    expected_outputs=[sf],
                    relevant_files=[sf],
                    priority=TaskPriority.NORMAL,
                )
                roles[tid] = AgentRole.CODING

            # Testing task depends on all coding subtasks
            t_test = f"task-{len(src_files)+1}"
            plan.add_or_update(
                task_id=t_test,
                title="Author and execute test suite",
                status=TaskStatus.PENDING,
                dependencies=[f"task-{i}" for i in range(1, len(src_files)+1)],
                priority=TaskPriority.HIGH,
            )
            roles[t_test] = AgentRole.TESTING

        elif is_bug_repair:
            # Bug repair pipeline: Debugging -> Testing -> Verification
            plan.add_or_update(
                task_id="task-1",
                title="Investigate root cause and apply patch",
                status=TaskStatus.READY,
                priority=TaskPriority.CRITICAL,
            )
            roles["task-1"] = AgentRole.DEBUGGING

            plan.add_or_update(
                task_id="task-2",
                title="Execute regression test suite",
                status=TaskStatus.PENDING,
                dependencies=["task-1"],
                priority=TaskPriority.HIGH,
            )
            roles["task-2"] = AgentRole.TESTING

        elif is_research:
            # Research & Coding collaboration
            plan.add_or_update(
                task_id="task-1",
                title="Explore architecture and identify target components",
                status=TaskStatus.READY,
                priority=TaskPriority.HIGH,
            )
            roles["task-1"] = AgentRole.RESEARCH

            plan.add_or_update(
                task_id="task-2",
                title="Implement proposed changes",
                status=TaskStatus.PENDING,
                dependencies=["task-1"],
                expected_outputs=src_files,
                priority=TaskPriority.NORMAL,
            )
            roles["task-2"] = AgentRole.CODING

        else:
            # Standard multi-stage pipeline: Coding -> Testing
            impl_target = src_files[0] if src_files else "src/implementation"
            test_target = test_files[0] if test_files else "tests/test_implementation"

            plan.add_or_update(
                task_id="task-1",
                title=f"Implement feature in {impl_target}",
                status=TaskStatus.READY,
                expected_outputs=src_files,
                priority=TaskPriority.HIGH,
            )
            roles["task-1"] = AgentRole.CODING

            plan.add_or_update(
                task_id="task-2",
                title=f"Author tests in {test_target} and verify",
                status=TaskStatus.PENDING,
                dependencies=["task-1"],
                expected_outputs=test_files,
                priority=TaskPriority.NORMAL,
            )
            roles["task-2"] = AgentRole.TESTING

        self.plan = plan
        self.assigned_roles = roles
        return plan, roles

    def spawn_worker_for_role(self, role: AgentRole, worker_id: str, assigned_skills: list[str]) -> WorkerAgent:
        """Provision isolated workspace and instantiate specialized worker."""
        worker_ws = self.workspace_manager.provision_worker_workspace(worker_id)
        w_config = WorkerConfig(
            worker_id=worker_id,
            role=role,
            workspace_path=str(worker_ws),
            assigned_skills=assigned_skills,
            read_only=(role == AgentRole.RESEARCH),
        )

        custom_model = self.worker_model_factory(role, worker_id) if self.worker_model_factory else None

        if role == AgentRole.RESEARCH:
            worker = ResearchWorker(w_config, self.config, self.workspace_manager, custom_model=custom_model, ui=self.ui)
        elif role == AgentRole.DEBUGGING:
            worker = DebuggingWorker(w_config, self.config, self.workspace_manager, custom_model=custom_model, ui=self.ui)
        elif role == AgentRole.TESTING:
            worker = TestingWorker(w_config, self.config, self.workspace_manager, custom_model=custom_model, ui=self.ui)
        else:
            worker = CodingWorker(w_config, self.config, self.workspace_manager, custom_model=custom_model, ui=self.ui)

        self.sidecar.register_worker(worker)
        return worker

    async def execute_multiagent_workflow(
        self,
        instruction: str,
        custom_plan: TaskPlan | None = None,
        custom_roles: dict[str, AgentRole] | None = None,
    ) -> tuple[CompletionStatus, HonestCompletionReport]:
        """Orchestrate multi-agent execution across worker sandboxes with safe integration."""
        start_time = time.perf_counter()
        self.ui.print_info("Initializing Multi-Agent Collaboration system...")

        # 1. Project discovery & memory retrieval
        project_summary: ProjectSummary = self.discovery.analyze()
        memory_text = self.retriever.retrieve_context(instruction=instruction, project_summary=project_summary)

        # 2. Skill selection
        skill_selection = self.skills.select_skills(
            instruction=instruction,
            manifest_files=project_summary.manifest_files,
            project_type=project_summary.project_type,
            memory_context=memory_text,
        )
        selected_skills = [s.name for s in skill_selection.selected_skills]

        # 3. Plan & role assignment
        if custom_plan and custom_roles:
            self.plan = custom_plan
            self.assigned_roles = custom_roles
        else:
            self.plan, self.assigned_roles = self.decompose_and_assign_roles(instruction)

        self.ui.print_info(f"Multi-Agent Plan established ({len(self.plan.tasks)} subtasks).")
        self.ui.print_plan(self.plan.to_dict_list())

        # 4. Orchestration Loop across DAG tasks
        worker_counter = 0

        while not self.plan.is_all_completed():
            ready_tasks = self.plan.get_ready_tasks()
            if not ready_tasks:
                if not self.plan.is_all_completed():
                    self.ui.print_warning("No tasks ready. Remaining tasks blocked.")
                break

            # Sequential mode check or parallel batching
            if self.ma_config.sequential_mode:
                batch = ready_tasks[:1]
            else:
                batch = ready_tasks[: self.ma_config.max_workers]

            # Spawn workers and dispatch assignments
            dispatch_coros = []
            active_proposals: list[ChangeProposal] = []

            for task in batch:
                worker_counter += 1
                role = self.assigned_roles.get(task.id, AgentRole.CODING)
                worker_id = f"worker-{role.value}-{worker_counter}"

                worker = self.spawn_worker_for_role(role, worker_id, selected_skills)
                task.mark_status(TaskStatus.RUNNING)
                self.ui.print_info(f"Delegating '{task.id}' to {role.value.upper()} agent ({worker_id})...")

                # Payload containing scoped memory and instructions
                payload = {
                    "instruction": f"{task.title}\nContext: {instruction}",
                    "memory_context": memory_text,
                    "expected_outputs": task.expected_outputs,
                }
                if self.collected_findings:
                    payload["findings"] = "\n".join(self.collected_findings)

                assignment = InterAgentMessage(
                    task_id=task.id,
                    sender_agent="coordinator",
                    recipient=worker_id,
                    message_type=MessageType.TASK_ASSIGNMENT,
                    payload=payload,
                )
                dispatch_coros.append(self.sidecar.dispatch_task(assignment))

            # Execute batch
            results: list[InterAgentMessage] = await asyncio.gather(*dispatch_coros)

            # Process worker results and collect change proposals
            for res in results:
                task = self.plan.get_task(res.task_id)
                if not task:
                    continue

                if res.message_type == MessageType.FAILURE:
                    err = res.payload.get("error", "Unknown worker error")
                    self.ui.print_error(f"Worker '{res.sender_agent}' failed on '{res.task_id}': {err}")
                    task.mark_status(TaskStatus.FAILED, evidence=err)

                elif res.message_type == MessageType.FINDINGS:
                    findings_text = res.payload.get("findings", "")
                    self.collected_findings.append(findings_text)
                    task.mark_status(TaskStatus.COMPLETED, evidence=findings_text[:200])
                    self.ui.print_info(f"Research findings collected from '{res.sender_agent}'.")

                elif res.message_type in (MessageType.CHANGE_PROPOSAL, MessageType.REVIEW_REQUEST):
                    prop_data = res.payload.get("proposal", {})
                    proposal = ChangeProposal.model_validate(prop_data)
                    active_proposals.append(proposal)
                    task.mark_status(TaskStatus.VERIFYING)

                elif res.message_type == MessageType.TASK_COMPLETED:
                    task.mark_status(TaskStatus.COMPLETED, evidence="Task completed by worker")

            # 5. Conflict Detection & Safe Integration
            if active_proposals:
                conflicts = self.workspace_manager.detect_conflicts(active_proposals)
                if conflicts:
                    self.ui.print_error(f"Integration conflict detected: {'; '.join(conflicts)}")
                    # Reject conflicting proposals and mark tasks blocked
                    for prop in active_proposals:
                        t = self.plan.get_task(prop.task_id)
                        if t:
                            t.mark_status(TaskStatus.BLOCKED, evidence="Merge conflict detected")
                else:
                    # Apply proposals cleanly into primary workspace
                    for prop in active_proposals:
                        ok, msg = self.workspace_manager.apply_proposal_to_primary(prop)
                        t = self.plan.get_task(prop.task_id)
                        if ok and t:
                            t.mark_status(TaskStatus.COMPLETED, evidence=msg)
                            self.approved_proposals.append(prop)
                            self.ui.print_info(f"Applied change proposal from '{prop.worker_id}' to integration workspace.")
                        elif t:
                            t.mark_status(TaskStatus.FAILED, evidence=msg)

        # 6. Central Verification Suite in primary integration workspace
        all_created = []
        all_modified = []
        for prop in self.approved_proposals:
            all_created.extend(prop.created_files)
            all_modified.extend(prop.modified_files)

        report = HonestCompletionReport(
            files_created=list(set(all_created)),
            files_modified=list(set(all_modified)),
        )

        if all_created or all_modified:
            test_cmd = self.verification.discover_test_command()
            if test_cmd:
                self.ui.print_info(f"Executing central integration verification: '{test_cmd}'...")
                check_result = await self.verification.run_check(test_cmd)
                report.checks.append(check_result)
                report.verified = check_result.passed
            else:
                report.unverified_notes.append("No automated test runner discovered for integration workspace.")
                report.verified = False
        else:
            report.verified = True  # Read-only task

        # Compute completion status
        if self.plan.is_all_completed():
            status = CompletionStatus.COMPLETED_VERIFIED if report.verified else CompletionStatus.COMPLETED_UNVERIFIED
        elif any(t.status == TaskStatus.COMPLETED for t in self.plan.tasks):
            status = CompletionStatus.PARTIALLY_COMPLETED
        else:
            status = CompletionStatus.FAILED

        # Shutdown sidecar workers
        self.sidecar.stop_all()
        return status, report
