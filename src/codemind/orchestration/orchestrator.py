"""Central Workflow Orchestrator coordinating planning, execution, verification, and recovery."""

from __future__ import annotations

import asyncio
import datetime
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from codemind.runtime.agent import CodeMindAgent

from codemind.cli.ui import TerminalUI
from codemind.config import CodeMindConfig, PermissionMode
from codemind.context.budget import ContextBudget
from codemind.context.discovery import ProjectDiscovery, ProjectSummary
from codemind.memory.distiller import MemoryDistiller
from codemind.memory.retriever import MemoryRetriever
from codemind.memory.store import SQLiteProjectMemory
from codemind.models import create_adapter
from codemind.models.base import ChatMessage, ModelAdapter
from codemind.orchestration.checkpoint import CheckpointManager, WorkflowCheckpoint
from codemind.orchestration.concurrency import ConcurrencyController
from codemind.orchestration.models import (
    CompletionStatus,
    ExecutionBudget,
    FailureCategory,
    OrchestrationStatus,
    RecoveryAction,
    RecoveryStrategy,
)
from codemind.orchestration.recovery import FailureClassifier
from codemind.planning.planner import Planner
from codemind.planning.task import (
    TaskComplexity,
    TaskItem,
    TaskPlan,
    TaskPriority,
    TaskStatus,
    VerificationCriterion,
)
from codemind.runtime.loop import AgentLoop
from codemind.runtime.state import AgentState
from codemind.security.permissions import PermissionChecker
from codemind.security.sandbox import WorkspaceSandbox
from codemind.sessions.manager import SessionManager
from codemind.skills.registry import SkillRegistry
from codemind.tools.base import ExecutionContext
from codemind.tools.registry import ToolRegistry
from codemind.verification.reporter import HonestCompletionReport
from codemind.verification.runner import VerificationRunner


class WorkflowOrchestrator:
    """Autonomous orchestrator executing complex software engineering workflows."""

    def __init__(
        self,
        config: CodeMindConfig,
        budget: ExecutionBudget | None = None,
        ui: TerminalUI | None = None,
        agent: CodeMindAgent | None = None,
    ):
        self.config = config
        self.budget = budget or ExecutionBudget()
        self.ui = ui or TerminalUI(plain_mode=config.plain_mode)
        self.workspace_root = Path(config.workspace_root).resolve()
        if agent is None:
            from codemind.runtime.agent import CodeMindAgent
            self.agent = CodeMindAgent(self.config, ui=self.ui)
        else:
            self.agent = agent

        # Subsystems
        self.discovery = self.agent.discovery
        self.memory = self.agent.memory
        self.retriever = self.agent.retriever
        self.distiller = self.agent.distiller
        self.skills = self.agent.skills
        self.sandbox = self.agent.sandbox
        self.permissions = self.agent.permission_checker
        self.tools = self.agent.tools
        self.verification = self.agent.verification
        self.checkpoint_manager = CheckpointManager(self.workspace_root)
        self.concurrency = ConcurrencyController(max_concurrent=self.budget.max_concurrent_operations)

        # State tracking
        self.status: OrchestrationStatus = OrchestrationStatus.INITIALIZING
        self.plan: TaskPlan = TaskPlan()
        self.active_session_id: str = f"cm-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.checkpoint: WorkflowCheckpoint | None = None
        self._is_paused: bool = False
        self._is_cancelled: bool = False
        self.total_turns_used: int = 0
        self.total_tool_calls_used: int = 0
        self.files_created: list[str] = []
        self.files_modified: list[str] = []

    def pause(self) -> None:
        """Signal orchestrator to safely pause after current atomic task."""
        self._is_paused = True
        self.status = OrchestrationStatus.PAUSED

    def cancel(self) -> None:
        """Signal orchestrator to cancel pending tasks and abort workflow gracefully."""
        self._is_cancelled = True
        self.status = OrchestrationStatus.CANCELLED
        for t in self.plan.tasks:
            if t.status in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.WAITING_FOR_APPROVAL):
                t.mark_status(TaskStatus.CANCELLED, evidence="Cancelled by user/system request.")

    def decompose_instruction(self, instruction: str) -> TaskPlan:
        """Decompose complex instruction into a structured dependency DAG."""
        plan = TaskPlan()
        inst_lower = instruction.lower()

        # Check if instruction is a multi-step task involving implementation + tests
        has_impl = any(w in inst_lower for w in ["implement", "create", "build", "add", "refactor", "update"])
        has_tests = any(w in inst_lower for w in ["test", "tests", "unittest", "pytest", "spec"])
        has_verify = any(w in inst_lower for w in ["verify", "verification", "check", "run"])

        # Detect extracted paths mentioned in instruction
        paths_found = re.findall(r"[\w/\.-]+\.(?:py|js|ts|tsx|json|sql|html|css|md)", instruction)
        src_files = [p for p in paths_found if not any(t in p.lower() for t in ["test", "spec"])]
        test_files = [p for p in paths_found if any(t in p.lower() for t in ["test", "spec"])]

        # Check for independent parallelizable components (e.g. "and also create", "independently")
        is_parallel_intent = "independent" in inst_lower or "parallel" in inst_lower or "both" in inst_lower and len(src_files) > 1

        if is_parallel_intent and len(src_files) >= 2:
            # Create independent parallel tasks
            for idx, sf in enumerate(src_files, 1):
                tid = f"task-{idx}"
                plan.add_or_update(
                    task_id=tid,
                    title=f"Implement component in {sf}",
                    status=TaskStatus.READY,
                    expected_outputs=[sf],
                    relevant_files=[sf],
                    verification_criteria=[VerificationCriterion(criterion_type="file_exists", target=sf)],
                    priority=TaskPriority.NORMAL,
                )
            # Add final integration verification step
            plan.add_or_update(
                task_id=f"task-{len(src_files)+1}",
                title="Verify integrated components and execute tests",
                status=TaskStatus.PENDING,
                dependencies=[f"task-{i}" for i in range(1, len(src_files)+1)],
                priority=TaskPriority.HIGH,
            )
        elif has_impl and has_tests:
            # Classic 3-step dependency pipeline: Implement -> Author Tests -> Run Verification
            impl_target = src_files[0] if src_files else "src/implementation"
            test_target = test_files[0] if test_files else "tests/test_implementation"

            t1 = plan.add_or_update(
                task_id="task-1",
                title=f"Implement feature logic ({impl_target})",
                status=TaskStatus.READY,
                expected_outputs=src_files,
                relevant_files=src_files,
                verification_criteria=[VerificationCriterion(criterion_type="file_exists", target=impl_target)] if src_files else [],
                priority=TaskPriority.HIGH,
            )
            t2 = plan.add_or_update(
                task_id="task-2",
                title=f"Author test suite ({test_target})",
                status=TaskStatus.PENDING,
                dependencies=["task-1"],
                expected_outputs=test_files,
                relevant_files=src_files + test_files,
                verification_criteria=[VerificationCriterion(criterion_type="file_exists", target=test_target)] if test_files else [],
                priority=TaskPriority.NORMAL,
            )
            t3 = plan.add_or_update(
                task_id="task-3",
                title="Execute automated verification and regression suite",
                status=TaskStatus.PENDING,
                dependencies=["task-2"],
                verification_criteria=[VerificationCriterion(criterion_type="test_passes", target="verification_runner")],
                priority=TaskPriority.CRITICAL,
            )
        else:
            # Single-step or direct task
            plan.add_or_update(
                task_id="task-1",
                title=instruction[:80],
                status=TaskStatus.READY,
                expected_outputs=paths_found,
                relevant_files=paths_found,
                priority=TaskPriority.NORMAL,
            )

        return plan

    async def execute_workflow(
        self,
        instruction: str,
        resume_session_id: str | None = None,
        custom_plan: TaskPlan | None = None,
    ) -> tuple[CompletionStatus, HonestCompletionReport]:
        """Execute complete orchestrator lifecycle across DAG tasks."""
        start_time = time.perf_counter()
        self.status = OrchestrationStatus.PLANNING

        # 1. Checkpoint resumption
        if resume_session_id:
            ckpt = self.checkpoint_manager.load_latest_checkpoint(resume_session_id)
            if ckpt:
                self.active_session_id = ckpt.session_id
                self.plan = self.checkpoint_manager.reconstruct_plan_from_checkpoint(ckpt)
                self.files_created = list(ckpt.files_created)
                self.files_modified = list(ckpt.files_modified)
                self.total_turns_used = ckpt.total_turns
                self.total_tool_calls_used = ckpt.total_tool_calls
                self.ui.print_info(f"Resumed workflow from checkpoint '{ckpt.checkpoint_id}'.")
            else:
                self.ui.print_error(f"No checkpoint found for session '{resume_session_id}'. Initializing fresh.")

        # 2. Project understanding & memory/skills
        project_summary: ProjectSummary = self.discovery.analyze()
        memory_text = self.retriever.retrieve_context(instruction=instruction, project_summary=project_summary)
        skills_selection = self.skills.select_skills(
            instruction=instruction,
            manifest_files=project_summary.manifest_files,
            project_type=project_summary.project_type,
            memory_context=memory_text,
        )

        # 3. Plan initialization if not resumed
        if not self.plan.tasks:
            if custom_plan:
                self.plan = custom_plan
            else:
                self.plan = self.decompose_instruction(instruction)

        # Validate DAG cycles
        cycles = self.plan.detect_cycles()
        if cycles:
            cycle_desc = " -> ".join(cycles[0])
            self.ui.print_error(f"Fatal planning error: Dependency cycle detected ({cycle_desc}).")
            for tid in cycles[0]:
                t = self.plan.get_task(tid)
                if t:
                    t.mark_status(TaskStatus.BLOCKED, evidence="Dependency cycle detected")
            self._save_checkpoint(instruction, is_completed=False)
            return CompletionStatus.BLOCKED, HonestCompletionReport(unverified_notes=[f"Dependency cycle: {cycle_desc}"])

        self.status = OrchestrationStatus.RUNNING
        self.ui.print_plan(self.plan.to_dict_list())
        self._save_checkpoint(instruction, is_completed=False)

        # 4. Orchestration Loop
        while not self.plan.is_all_completed() and not self._is_paused and not self._is_cancelled:
            # Check budgets
            if self.total_turns_used >= self.budget.max_turns:
                self.ui.print_error(f"Budget exceeded: max turns reached ({self.budget.max_turns}).")
                break
            if self.total_tool_calls_used >= self.budget.max_tool_calls:
                self.ui.print_error(f"Budget exceeded: max tool calls reached ({self.budget.max_tool_calls}).")
                break
            if (time.perf_counter() - start_time) > self.budget.max_execution_time_seconds:
                self.ui.print_error("Budget exceeded: max execution time elapsed.")
                break

            ready_tasks = self.plan.get_ready_tasks()
            if not ready_tasks:
                # If no tasks are ready and not all completed, we are blocked
                if not self.plan.is_all_completed():
                    self.ui.print_warning("No tasks are READY. Remaining tasks are blocked by incomplete dependencies.")
                break

            # Filter ready tasks using ConcurrencyController
            parallel_candidates = self.concurrency.check_task_conflicts(ready_tasks, self.plan)

            # Execute batch (sequential or safe parallel)
            tasks_to_run = parallel_candidates[: self.budget.max_concurrent_operations]
            if len(tasks_to_run) > 1:
                # Parallel dispatch
                coros = [self._execute_single_task(t, instruction, project_summary, memory_text, skills_selection) for t in tasks_to_run]
                results = await asyncio.gather(*coros, return_exceptions=True)
            else:
                # Sequential dispatch
                results = [await self._execute_single_task(tasks_to_run[0], instruction, project_summary, memory_text, skills_selection)]

            # Checkpoint after batch
            self._save_checkpoint(instruction, is_completed=self.plan.is_all_completed())

        # 5. Final verification & report assembly
        report = HonestCompletionReport(
            files_created=list(set(self.files_created)),
            files_modified=list(set(self.files_modified)),
        )

        # Run project-level automated test verification if files were modified
        if (self.files_created or self.files_modified) and self.config.runtime.auto_verify:
            test_cmd = self.verification.discover_test_command()
            if test_cmd:
                self.ui.print_info(f"Running automated project verification: '{test_cmd}'...")
                check_result = await self.verification.run_check(test_cmd)
                report.checks.append(check_result)
                report.verified = check_result.passed
            else:
                report.unverified_notes.append("No automated test runner discovered for this project.")
                report.verified = False
        elif not self.files_created and not self.files_modified:
            report.verified = True  # Read-only task

        # Determine completion status
        completion_status = self._determine_completion_status(report)
        self._save_checkpoint(instruction, is_completed=(completion_status == CompletionStatus.COMPLETED_VERIFIED))

        # Distill memory if accomplished
        if self.files_created or self.files_modified:
            dummy_state = AgentState(
                session_id=self.active_session_id,
                workspace_root=str(self.workspace_root),
                task_instruction=instruction,
                files_created=self.files_created,
                files_modified=self.files_modified,
            )
            self.distiller.distill(dummy_state, report, project_summary)

        return completion_status, report

    async def _execute_single_task(
        self,
        task: TaskItem,
        instruction: str,
        project_summary: ProjectSummary,
        memory_text: str,
        skills_selection: Any,
    ) -> bool:
        """Execute a single task node with permission gating, failure classification, and verification."""
        task.mark_status(TaskStatus.RUNNING)
        self.ui.print_info(f"Dispatching task '{task.id}': {task.title}")

        # Check permissions
        if self.config.security.permission_mode == PermissionMode.SUPERVISED and "delete" in task.title.lower():
            task.mark_status(TaskStatus.WAITING_FOR_APPROVAL)
            self.ui.print_warning(f"Task '{task.id}' requires user approval before execution.")
            # If supervised mode without interactive human approval hook, fail gracefully
            task.mark_status(TaskStatus.BLOCKED, evidence="Awaiting manual approval")
            return False

        # Build subtask prompt
        subtask_prompt = (
            f"TASK GOAL: {task.title}\n"
            f"Description: {task.description or task.title}\n"
            f"Context: {instruction}\n"
        )
        if task.expected_outputs:
            subtask_prompt += f"Expected outputs: {', '.join(task.expected_outputs)}\n"
        subtask_prompt += "Ensure valid protocol v1 JSON action envelopes ('tool_call', 'plan', or 'final') are emitted.\n"

        # Use configured Agent
        agent = self.agent
        await agent.initialize(resume_session_id=self.active_session_id)

        try:
            state = await agent.run_task(subtask_prompt)
            self.total_turns_used += state.turn_count
            self.total_tool_calls_used += state.total_tool_calls
            self.files_created.extend(state.files_created)
            self.files_modified.extend(state.files_modified)

            # Check verification criteria
            task.mark_status(TaskStatus.VERIFYING)
            for crit in task.verification_criteria:
                if crit.criterion_type == "file_exists":
                    target_path = self.workspace_root / crit.target
                    crit.satisfied = target_path.exists()
                    crit.actual_value = "exists" if crit.satisfied else "missing"
                elif crit.criterion_type == "test_passes":
                    test_cmd = self.verification.discover_test_command()
                    if test_cmd:
                        res = await self.verification.run_check(test_cmd)
                        crit.satisfied = res.passed
                        crit.actual_value = f"{res.passed_count} passed, {res.failed_count} failed"
                    else:
                        crit.satisfied = False
                        crit.message = "No test runner discovered"

            completed_ok, reason = self.plan.mark_task_completed(task.id, evidence=state.final_content[:300])
            if completed_ok:
                self.ui.print_info(f"Task '{task.id}' COMPLETED and verified.")
                return True
            else:
                # Handle criteria failure with intelligent retry
                self.ui.print_warning(f"Task '{task.id}' verification unmet: {reason}")
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    task.mark_status(TaskStatus.RETRYING, evidence=f"Retry {task.retry_count}: {reason}")
                    self.ui.print_info(f"Retrying task '{task.id}' (Attempt {task.retry_count}/{task.max_retries})...")
                    await asyncio.sleep(1.0)
                    retry_instruction = (
                        f"{instruction}\n"
                        f"NOTE: Previous attempt failed verification: {reason}. "
                        f"Ensure all expected files are created and valid protocol v1 JSON emitted."
                    )
                    return await self._execute_single_task(task, retry_instruction, project_summary, memory_text, skills_selection)
                return False

        except Exception as ex:
            # Classify error
            strategy: RecoveryStrategy = FailureClassifier.classify_model_failure(str(ex))
            self.ui.print_error(f"Task '{task.id}' failed ({strategy.category.value}): {strategy.message}")

            if strategy.retryable and task.retry_count < task.max_retries:
                task.retry_count += 1
                task.mark_status(TaskStatus.RETRYING, evidence=f"Attempt {task.retry_count}: {strategy.guidance}")
                await asyncio.sleep(strategy.backoff_seconds)
                # Retry recursively
                return await self._execute_single_task(task, instruction, project_summary, memory_text, skills_selection)
            else:
                task.mark_status(TaskStatus.FAILED, evidence=f"Fatal failure: {strategy.message}")
                return False

    def _determine_completion_status(self, report: HonestCompletionReport) -> CompletionStatus:
        """Compute authoritative completion status."""
        if self._is_cancelled:
            return CompletionStatus.CANCELLED
        if self.plan.is_all_completed():
            if report.verified:
                return CompletionStatus.COMPLETED_VERIFIED
            else:
                return CompletionStatus.COMPLETED_UNVERIFIED
        completed_count = len([t for t in self.plan.tasks if t.status == TaskStatus.COMPLETED])
        if completed_count > 0:
            return CompletionStatus.PARTIALLY_COMPLETED
        if any(t.status == TaskStatus.BLOCKED for t in self.plan.tasks):
            return CompletionStatus.BLOCKED
        return CompletionStatus.FAILED

    def _save_checkpoint(self, instruction: str, is_completed: bool = False) -> None:
        """Atomically persist current orchestrator execution checkpoint."""
        ckpt = WorkflowCheckpoint(
            session_id=self.active_session_id,
            workspace_root=str(self.workspace_root),
            instruction=instruction,
            tasks=self.plan.to_dict_list(),
            completed_task_ids=[t.id for t in self.plan.tasks if t.status == TaskStatus.COMPLETED],
            pending_task_ids=[t.id for t in self.plan.tasks if t.status in (TaskStatus.PENDING, TaskStatus.READY)],
            failed_task_ids=[t.id for t in self.plan.tasks if t.status in (TaskStatus.FAILED, TaskStatus.CANCELLED)],
            files_created=list(set(self.files_created)),
            files_modified=list(set(self.files_modified)),
            total_turns=self.total_turns_used,
            total_tool_calls=self.total_tool_calls_used,
            is_completed=is_completed,
        )
        self.checkpoint = ckpt
        self.checkpoint_manager.save_checkpoint_atomic(ckpt)
