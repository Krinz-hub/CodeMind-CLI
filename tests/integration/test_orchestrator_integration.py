"""Integration tests for WorkflowOrchestrator with mock adapters and full DAG execution."""

import asyncio
from pathlib import Path

from codemind.config import CodeMindConfig, ModelProvider, PermissionMode
from codemind.models.mock import MockModelAdapter
from codemind.orchestration.checkpoint import CheckpointManager
from codemind.orchestration.models import CompletionStatus, ExecutionBudget
from codemind.orchestration.orchestrator import WorkflowOrchestrator
from codemind.planning.task import TaskPlan, TaskStatus, VerificationCriterion
from tests.base import BaseAgentTestCase


class TestOrchestratorIntegration(BaseAgentTestCase):
    def test_workflow_orchestration_lifecycle(self) -> None:
        ws_str = str(self.workspace_root)
        self.create_file("pyproject.toml", '[project]\nname = "demo-pkg"\n')
        self.create_file("src/__init__.py", "")

        cfg = CodeMindConfig(
            workspace_root=ws_str,
            plain_mode=True,
            model={"provider": ModelProvider.MOCK, "model_name": "mock"},
            security={"permission_mode": PermissionMode.TRUSTED},
        )

        orchestrator = WorkflowOrchestrator(
            config=cfg,
            budget=ExecutionBudget(max_turns=10, max_tool_calls=15),
        )

        # Build a 2-step custom plan with explicit verification criteria
        custom_plan = TaskPlan()
        t1 = custom_plan.add_or_update(
            task_id="step-1",
            title="Create string helper module",
            status=TaskStatus.READY,
            expected_outputs=["src/str_helper.py"],
            relevant_files=["src/str_helper.py"],
        )
        t1.verification_criteria.append(
            VerificationCriterion(criterion_type="file_exists", target="src/str_helper.py")
        )

        # Define mock behavior for the agent when running subtasks
        assert isinstance(orchestrator.agent.model, MockModelAdapter)
        orchestrator.agent.model.queue_response(
            '{"protocol_version": "1", "type": "tool_call", "tool": "create_file", "arguments": {"path": "src/str_helper.py", "content": "def shout(s: str) -> str: return s.upper() + \'!\'\\n"}, "reason": "Create helper"}'
        )
        orchestrator.agent.model.queue_response(
            '{"protocol_version": "1", "type": "final", "content": "Created string helper in src/str_helper.py", "summary": ["Created helper"]}'
        )

        status, report = asyncio.run(
            orchestrator.execute_workflow(
                instruction="Implement string helper in src/str_helper.py",
                custom_plan=custom_plan,
            )
        )

        # Verify task completed
        self.assertEqual(custom_plan.tasks[0].status, TaskStatus.COMPLETED)
        self.assertTrue((self.workspace_root / "src" / "str_helper.py").exists())

        # Verify checkpoint written
        mgr = CheckpointManager(self.workspace_root)
        ckpt = mgr.load_latest_checkpoint(orchestrator.active_session_id)
        self.assertIsNotNone(ckpt)
        assert ckpt is not None
        self.assertIn("step-1", ckpt.completed_task_ids)

    def test_workflow_pause_and_cancel(self) -> None:
        ws_str = str(self.workspace_root)
        cfg = CodeMindConfig(
            workspace_root=ws_str,
            plain_mode=True,
            model={"provider": ModelProvider.MOCK, "model_name": "mock"},
        )
        orchestrator = WorkflowOrchestrator(config=cfg)

        plan = TaskPlan()
        plan.add_or_update("t1", "Initial task", TaskStatus.PENDING)
        plan.add_or_update("t2", "Subsequent task", TaskStatus.PENDING, dependencies=["t1"])
        orchestrator.plan = plan

        # Cancel workflow
        orchestrator.cancel()
        self.assertEqual(plan.tasks[0].status, TaskStatus.CANCELLED)
        self.assertEqual(plan.tasks[1].status, TaskStatus.CANCELLED)
