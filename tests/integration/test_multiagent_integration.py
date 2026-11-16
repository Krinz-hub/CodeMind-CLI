"""Integration tests for Multi-Agent Collaboration and Sidecar Runtime."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from codemind.config import CodeMindConfig, ModelProvider, PermissionMode
from codemind.models.mock import MockModelAdapter
from codemind.multiagent.coordinator import MultiAgentCoordinator
from codemind.multiagent.models import AgentRole, ChangeProposal, MultiAgentConfig
from codemind.orchestration.models import CompletionStatus
from codemind.planning.task import TaskPlan, TaskStatus


class TestMultiAgentIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="codemind_ma_int_")
        self.workspace_root = Path(self.temp_dir)
        (self.workspace_root / "src").mkdir(parents=True, exist_ok=True)
        (self.workspace_root / "tests").mkdir(parents=True, exist_ok=True)

        # Basic pyproject.toml
        (self.workspace_root / "pyproject.toml").write_text(
            '[project]\nname = "multiagent-demo"\nversion = "0.1.0"\n'
        )

        self.global_config = CodeMindConfig(
            workspace_root=str(self.workspace_root),
            plain_mode=True,
            model={"provider": ModelProvider.MOCK, "model_name": "mock-codemind"},
            security={"permission_mode": PermissionMode.TRUSTED},
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_end_to_end_cooperative_multiagent_delivery(self):
        """Verify full multi-agent pipeline: Research -> Coding -> Integration -> Central Verification."""
        # Initial file
        (self.workspace_root / "src" / "greeting.py").write_text("def base_greet(): return 'hello'\n")

        # Mock adapter responses for workers
        def worker_model_factory(role: AgentRole, worker_id: str) -> MockModelAdapter:
            adapter = MockModelAdapter()
            if role == AgentRole.RESEARCH:
                # Research worker inspects and reports findings
                adapter.queue_response(
                    '{"protocol_version": "1", "type": "tool_call", "tool": "read_file", "arguments": {"path": "src/greeting.py"}, "reason": "Inspect greeting"}'
                )
                adapter.queue_response(
                    '{"protocol_version": "1", "type": "final", "content": "Analyzed greeting module. Ready for personalization feature."}'
                )
            elif role == AgentRole.CODING:
                # Coding worker creates feature in its isolated workspace
                adapter.queue_response(
                    '{"protocol_version": "1", "type": "tool_call", "tool": "create_file", "arguments": {"path": "src/personal.py", "content": "def greet(name: str) -> str: return f\'Hello, {name}!\'\\n"}, "reason": "Implement personalized greeting"}'
                )
                adapter.queue_response(
                    '{"protocol_version": "1", "type": "final", "content": "Created personalized greeting feature."}'
                )
            return adapter

        coordinator = MultiAgentCoordinator(
            config=self.global_config,
            multiagent_config=MultiAgentConfig(max_workers=2, sequential_mode=True),
            worker_model_factory=worker_model_factory,
        )

        # Define 2-step custom plan
        plan = TaskPlan()
        plan.add_or_update(
            task_id="t-1",
            title="Research greeting architecture",
            status=TaskStatus.READY,
        )
        plan.add_or_update(
            task_id="t-2",
            title="Implement personalized greeting in src/personal.py",
            status=TaskStatus.PENDING,
            dependencies=["t-1"],
            expected_outputs=["src/personal.py"],
        )

        roles = {
            "t-1": AgentRole.RESEARCH,
            "t-2": AgentRole.CODING,
        }

        status, report = asyncio.run(
            coordinator.execute_multiagent_workflow(
                instruction="Research greeting and implement personalized greeting in src/personal.py",
                custom_plan=plan,
                custom_roles=roles,
            )
        )

        # Verify execution and integration
        self.assertTrue(plan.is_all_completed())
        self.assertEqual(len(coordinator.collected_findings), 1)
        self.assertIn("Analyzed greeting module", coordinator.collected_findings[0])

        # Verify merged into primary integration workspace
        primary_personal_file = self.workspace_root / "src" / "personal.py"
        self.assertTrue(primary_personal_file.exists())
        self.assertIn("Hello, {name}!", primary_personal_file.read_text())

    def test_debugging_and_test_driven_repair_collaboration(self):
        """Verify Debugging worker isolates bug, fixes code in sandbox, and integrates cleanly."""
        # Broken initial function
        (self.workspace_root / "src" / "calc.py").write_text("def divide(a, b): return a * b  # BUG: should divide\n")

        def worker_model_factory(role: AgentRole, worker_id: str) -> MockModelAdapter:
            adapter = MockModelAdapter()
            if role == AgentRole.DEBUGGING:
                adapter.queue_response(
                    '{"protocol_version": "1", "type": "tool_call", "tool": "write_file", "arguments": {"path": "src/calc.py", "content": "def divide(a, b):\\n    if b == 0:\\n        raise ValueError(\'Division by zero\')\\n    return a / b\\n"}, "reason": "Fix divide calculation bug"}'
                )
                adapter.queue_response(
                    '{"protocol_version": "1", "type": "final", "content": "Bug repaired in src/calc.py."}'
                )
            return adapter

        coordinator = MultiAgentCoordinator(
            config=self.global_config,
            multiagent_config=MultiAgentConfig(max_workers=2),
            worker_model_factory=worker_model_factory,
        )

        plan = TaskPlan()
        plan.add_or_update("t-fix", "Fix bug in src/calc.py", TaskStatus.READY)
        roles = {"t-fix": AgentRole.DEBUGGING}

        status, report = asyncio.run(
            coordinator.execute_multiagent_workflow(
                instruction="Fix divide bug in src/calc.py",
                custom_plan=plan,
                custom_roles=roles,
            )
        )

        self.assertTrue(plan.is_all_completed())
        fixed_content = (self.workspace_root / "src" / "calc.py").read_text()
        self.assertIn("return a / b", fixed_content)
        self.assertIn("raise ValueError", fixed_content)

    def test_parallel_independent_workers_no_conflict(self):
        """Verify multiple independent coding tasks run concurrently and merge cleanly."""
        def worker_model_factory(role: AgentRole, worker_id: str) -> MockModelAdapter:
            adapter = MockModelAdapter()
            if "worker-coding-1" in worker_id:
                adapter.queue_response(
                    '{"protocol_version": "1", "type": "tool_call", "tool": "create_file", "arguments": {"path": "src/module_a.py", "content": "def func_a(): return \'A\'\\n"}, "reason": "Implement A"}'
                )
                adapter.queue_response('{"protocol_version": "1", "type": "final", "content": "A done"}')
            elif "worker-coding-2" in worker_id:
                adapter.queue_response(
                    '{"protocol_version": "1", "type": "tool_call", "tool": "create_file", "arguments": {"path": "src/module_b.py", "content": "def func_b(): return \'B\'\\n"}, "reason": "Implement B"}'
                )
                adapter.queue_response('{"protocol_version": "1", "type": "final", "content": "B done"}')
            return adapter

        coordinator = MultiAgentCoordinator(
            config=self.global_config,
            multiagent_config=MultiAgentConfig(max_workers=2, sequential_mode=False),
            worker_model_factory=worker_model_factory,
        )

        plan = TaskPlan()
        plan.add_or_update("t-a", "Implement A", TaskStatus.READY)
        plan.add_or_update("t-b", "Implement B", TaskStatus.READY)
        roles = {"t-a": AgentRole.CODING, "t-b": AgentRole.CODING}

        status, report = asyncio.run(
            coordinator.execute_multiagent_workflow(
                instruction="Implement module A and module B in parallel",
                custom_plan=plan,
                custom_roles=roles,
            )
        )

        self.assertTrue(plan.is_all_completed())
        self.assertTrue((self.workspace_root / "src" / "module_a.py").exists())
        self.assertTrue((self.workspace_root / "src" / "module_b.py").exists())

    def test_concurrent_conflict_blocking(self):
        """Verify coordinator conflict detector prevents conflicting mutations to the same file."""
        def worker_model_factory(role: AgentRole, worker_id: str) -> MockModelAdapter:
            adapter = MockModelAdapter()
            # Both workers mutate src/shared.py concurrently
            adapter.queue_response(
                f'{{"protocol_version": "1", "type": "tool_call", "tool": "create_file", "arguments": {{"path": "src/shared.py", "content": "version_{worker_id}"}}, "reason": "Mutate shared"}}'
            )
            adapter.queue_response('{"protocol_version": "1", "type": "final", "content": "Done"}')
            return adapter

        coordinator = MultiAgentCoordinator(
            config=self.global_config,
            multiagent_config=MultiAgentConfig(max_workers=2, sequential_mode=False),
            worker_model_factory=worker_model_factory,
        )

        plan = TaskPlan()
        plan.add_or_update("t-1", "Worker 1 edits shared", TaskStatus.READY)
        plan.add_or_update("t-2", "Worker 2 edits shared", TaskStatus.READY)
        roles = {"t-1": AgentRole.CODING, "t-2": AgentRole.CODING}

        status, report = asyncio.run(
            coordinator.execute_multiagent_workflow(
                instruction="Both workers mutate shared.py concurrently",
                custom_plan=plan,
                custom_roles=roles,
            )
        )

        # Conflict must be detected and tasks marked BLOCKED
        self.assertEqual(plan.get_task("t-1").status, TaskStatus.BLOCKED)
        self.assertEqual(plan.get_task("t-2").status, TaskStatus.BLOCKED)
        # Primary workspace file must NOT exist (unverified/corrupted state rejected)
        self.assertFalse((self.workspace_root / "src" / "shared.py").exists())


if __name__ == "__main__":
    unittest.main()
