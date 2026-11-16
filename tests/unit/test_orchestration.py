"""Unit tests for Phase 6 Workflow Orchestration, DAG planning, and failure recovery."""

import tempfile
from pathlib import Path

from codemind.orchestration.checkpoint import CheckpointManager, WorkflowCheckpoint
from codemind.orchestration.concurrency import ConcurrencyController
from codemind.orchestration.models import (
    CompletionStatus,
    ExecutionBudget,
    FailureCategory,
    RecoveryAction,
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
from tests.base import BaseAgentTestCase


class TestOrchestration(BaseAgentTestCase):
    def test_dag_topological_sort_and_readiness(self) -> None:
        plan = TaskPlan()
        plan.add_or_update("t1", "Setup workspace", TaskStatus.PENDING, priority=TaskPriority.HIGH)
        plan.add_or_update("t2", "Build core module", TaskStatus.PENDING, dependencies=["t1"], priority=TaskPriority.NORMAL)
        plan.add_or_update("t3", "Author tests", TaskStatus.PENDING, dependencies=["t2"], priority=TaskPriority.NORMAL)
        plan.add_or_update("t4", "Documentation", TaskStatus.PENDING, dependencies=["t1"], priority=TaskPriority.LOW)

        # Initially, only t1 should be ready
        ready = plan.get_ready_tasks()
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].id, "t1")

        # Complete t1
        t1 = plan.get_task("t1")
        assert t1 is not None
        t1.mark_status(TaskStatus.COMPLETED)

        # Now t2 and t4 should be ready, with t2 (NORMAL) prioritized over t4 (LOW)
        ready = plan.get_ready_tasks()
        ready_ids = [t.id for t in ready]
        self.assertEqual(len(ready), 2)
        self.assertIn("t2", ready_ids)
        self.assertIn("t4", ready_ids)
        self.assertEqual(ready_ids[0], "t2")  # Higher priority first

        # Topological order
        topo = plan.get_topological_order()
        topo_ids = [t.id for t in topo]
        self.assertEqual(topo_ids.index("t1"), 0)
        self.assertTrue(topo_ids.index("t2") < topo_ids.index("t3"))

    def test_dag_cycle_detection(self) -> None:
        plan = TaskPlan()
        plan.add_or_update("a", "Task A", TaskStatus.PENDING, dependencies=["c"])
        plan.add_or_update("b", "Task B", TaskStatus.PENDING, dependencies=["a"])
        plan.add_or_update("c", "Task C", TaskStatus.PENDING, dependencies=["b"])

        cycles = plan.detect_cycles()
        self.assertTrue(len(cycles) > 0)
        # Verify nodes in cycle
        cycle_nodes = set(cycles[0])
        self.assertTrue({"a", "b", "c"}.issubset(cycle_nodes))

    def test_parallelization_conflict_detection(self) -> None:
        plan = TaskPlan()
        # Task 1 & 2 modify different files -> safe
        plan.add_or_update("t1", "Module A", TaskStatus.READY, expected_outputs=["src/a.py"])
        plan.add_or_update("t2", "Module B", TaskStatus.READY, expected_outputs=["src/b.py"])
        can_par, msg = plan.can_parallelize("t1", "t2")
        self.assertTrue(can_par)

        # Task 3 modifies src/a.py -> conflict with t1
        plan.add_or_update("t3", "Module A Variant", TaskStatus.READY, expected_outputs=["src/a.py"])
        can_par, msg = plan.can_parallelize("t1", "t3")
        self.assertFalse(can_par)
        self.assertIn("Shared mutable files", msg)

        # Task 4 reads src/a.py -> read/write conflict with t1
        plan.add_or_update("t4", "Module A Reader", TaskStatus.READY, relevant_files=["src/a.py"])
        can_par, msg = plan.can_parallelize("t1", "t4")
        self.assertFalse(can_par)

    def test_verification_criteria_enforcement(self) -> None:
        plan = TaskPlan()
        t1 = plan.add_or_update("t1", "Implement math helper", TaskStatus.RUNNING)
        crit = VerificationCriterion(
            criterion_type="file_exists",
            target="src/math.py",
            satisfied=False,
        )
        t1.verification_criteria.append(crit)

        # Attempt to mark complete while unsatisfied -> must fail
        ok, reason = plan.mark_task_completed("t1")
        self.assertFalse(ok)
        self.assertEqual(t1.status, TaskStatus.FAILED)
        self.assertIn("Unsatisfied verification criteria", reason)

        # Now satisfy criterion
        crit.satisfied = True
        ok, reason = plan.mark_task_completed("t1", evidence="Verified file exists")
        self.assertTrue(ok)
        self.assertEqual(t1.status, TaskStatus.COMPLETED)

    def test_failure_classification(self) -> None:
        # 1. Permission Denied -> Not retryable, terminate
        strat = FailureClassifier.classify_tool_failure("run_command", "Permission denied: access to /etc/shadow prohibited")
        self.assertEqual(strat.category, FailureCategory.PERMISSION_DENIED)
        self.assertEqual(strat.action, RecoveryAction.TERMINATE_GRACEFULLY)
        self.assertFalse(strat.retryable)

        # 2. Test Failure -> Test-driven repair
        strat = FailureClassifier.classify_tool_failure("run_command", "FAILED (failures=1): AssertionError: expected 5 got 4")
        self.assertEqual(strat.category, FailureCategory.TEST_FAILURE)
        self.assertEqual(strat.action, RecoveryAction.TEST_DRIVEN_REPAIR)
        self.assertTrue(strat.retryable)

        # 3. Build / Syntax Error -> Build repair
        strat = FailureClassifier.classify_tool_failure("apply_patch", "SyntaxError: invalid syntax at line 24")
        self.assertEqual(strat.category, FailureCategory.BUILD_FAILURE)
        self.assertEqual(strat.action, RecoveryAction.BUILD_REPAIR)

        # 4. Patch target mismatch -> Refresh file context
        strat = FailureClassifier.classify_tool_failure("apply_patch", "Failed to apply patch: could not match target")
        self.assertEqual(strat.category, FailureCategory.TOOL_EXECUTION_FAILURE)
        self.assertEqual(strat.action, RecoveryAction.REFRESH_FILE_CONTEXT)

        # 5. Missing dependency -> Replan
        strat = FailureClassifier.classify_tool_failure("run_command", "ModuleNotFoundError: No module named 'pydantic'")
        self.assertEqual(strat.category, FailureCategory.MISSING_DEPENDENCY)
        self.assertEqual(strat.action, RecoveryAction.REPLAN)

    def test_atomic_checkpoint_persistence_and_recovery(self) -> None:
        mgr = CheckpointManager(self.workspace_root)
        ckpt = WorkflowCheckpoint(
            session_id="cm-session-123",
            workspace_root=str(self.workspace_root),
            instruction="Implement billing module and integration tests",
            current_task_id="task-2",
            execution_position=2,
            tasks=[
                {"id": "task-1", "title": "Create invoice model", "status": "completed", "evidence": "Model defined"},
                {"id": "task-2", "title": "Implement payment gateway", "status": "running", "dependencies": ["task-1"]},
                {"id": "task-3", "title": "Verify payment flows", "status": "pending", "dependencies": ["task-2"]},
            ],
            completed_task_ids=["task-1"],
            pending_task_ids=["task-3"],
            files_created=["src/invoice.py"],
            total_turns=4,
            total_tool_calls=2,
        )

        saved_path = mgr.save_checkpoint_atomic(ckpt)
        self.assertTrue(saved_path.is_file())

        # Load latest
        loaded = mgr.load_latest_checkpoint("cm-session-123")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.current_task_id, "task-2")
        self.assertEqual(len(loaded.completed_task_ids), 1)

        # Reconstruct plan
        reconstructed = mgr.reconstruct_plan_from_checkpoint(loaded)
        self.assertEqual(len(reconstructed.tasks), 3)
        self.assertEqual(reconstructed.tasks[0].status, TaskStatus.COMPLETED)
        self.assertEqual(reconstructed.tasks[1].status, TaskStatus.RUNNING)
        self.assertEqual(reconstructed.tasks[2].status, TaskStatus.PENDING)

    def test_concurrency_controller(self) -> None:
        ctrl = ConcurrencyController(max_concurrent=2)
        plan = TaskPlan()
        t1 = plan.add_or_update("t1", "Task 1", TaskStatus.READY, relevant_files=["src/a.py"])
        t2 = plan.add_or_update("t2", "Task 2", TaskStatus.READY, relevant_files=["src/b.py"])
        t3 = plan.add_or_update("t3", "Task 3", TaskStatus.READY, relevant_files=["src/a.py"])

        # Filter candidate tasks: t1 and t2 can run concurrently; t3 conflicts with t1
        safe_batch = ctrl.check_task_conflicts([t1, t2, t3], plan)
        self.assertEqual(len(safe_batch), 2)
        self.assertEqual(safe_batch[0].id, "t1")
        self.assertEqual(safe_batch[1].id, "t2")
