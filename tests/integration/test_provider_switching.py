"""Integration tests for model provider switching and multi-agent execution with custom model."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from codemind.cli.main import app
from codemind.config import CodeMindConfig, ModelProvider, PermissionMode
from codemind.models.base import ChatMessage
from codemind.models.custom import CodeMindCustomAdapter, FallbackAwareModelAdapter
from codemind.models.mock import MockModelAdapter
from codemind.multiagent.coordinator import MultiAgentCoordinator
from codemind.multiagent.models import AgentRole, MultiAgentConfig
from codemind.planning.task import TaskPlan, TaskStatus


class TestProviderSwitchingIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="codemind_switch_test_")
        self.workspace_root = Path(self.temp_dir)
        (self.workspace_root / "src").mkdir(parents=True, exist_ok=True)
        (self.workspace_root / "tests").mkdir(parents=True, exist_ok=True)
        (self.workspace_root / "pyproject.toml").write_text('[project]\nname = "switch-demo"\n')

        self.runner = CliRunner()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cli_models_use_and_compare(self):
        """Verify switching provider via CLI persists in .codemind/config.json."""
        ws_str = str(self.workspace_root)

        # 1. Switch to custom provider
        res_use = self.runner.invoke(
            app,
            ["models", "use", "codemind", "-p", "codemind-custom", "-e", "http://127.0.0.1:8000/v1", "--plain", "-w", ws_str],
        )
        self.assertEqual(res_use.exit_code, 0)
        self.assertIn("codemind", res_use.output)

        # 2. Verify config persisted
        config = CodeMindConfig.load(workspace_dir=self.workspace_root)
        self.assertEqual(config.model.model_name, "codemind")
        self.assertEqual(config.model.provider, ModelProvider.CODEMIND_CUSTOM)
        self.assertEqual(config.model.endpoint, "http://127.0.0.1:8000/v1")

        # 3. Check compare output
        res_comp = self.runner.invoke(app, ["models", "compare", "--plain", "-w", ws_str])
        self.assertEqual(res_comp.exit_code, 0)
        self.assertIn("codemind-custom", res_comp.output)
        self.assertIn("ollama", res_comp.output)

    def test_multiagent_execution_with_fallback_provider(self):
        """Verify MultiAgentCoordinator completes workflow when custom model falls back to secondary."""
        # Unreachable custom model
        primary_adapter = CodeMindCustomAdapter(
            endpoint="http://127.0.0.1:59999/v1",
            model_name="codemind",
            timeout_seconds=1,
        )

        # Mock fallback providing valid responses
        mock_fallback = MockModelAdapter()
        mock_fallback.queue_response(
            '{"protocol_version": "1", "type": "tool_call", "tool": "create_file", "arguments": {"path": "src/service.py", "content": "def run(): return 42\\n"}, "reason": "Implement service"}'
        )
        mock_fallback.queue_response('{"protocol_version": "1", "type": "final", "content": "Feature implemented"}')

        composite = FallbackAwareModelAdapter(primary_adapter, mock_fallback, enable_fallback=True)

        cfg = CodeMindConfig(
            workspace_root=str(self.workspace_root),
            plain_mode=True,
            model={"provider": ModelProvider.MOCK, "model_name": "mock"},
            security={"permission_mode": PermissionMode.TRUSTED},
        )

        # Worker factory injecting composite adapter
        def worker_model_factory(role: AgentRole, worker_id: str):
            return composite

        coord = MultiAgentCoordinator(
            cfg,
            multiagent_config=MultiAgentConfig(max_workers=1),
            worker_model_factory=worker_model_factory,
        )

        plan = TaskPlan()
        plan.add_or_update("t-1", "Implement service in src/service.py", TaskStatus.READY)
        roles = {"t-1": AgentRole.CODING}

        status, report = asyncio.run(
            coord.execute_multiagent_workflow(
                "Implement service in src/service.py",
                custom_plan=plan,
                custom_roles=roles,
            )
        )

        # Workflow succeeded
        self.assertTrue(plan.is_all_completed())
        self.assertTrue((self.workspace_root / "src" / "service.py").exists())
        # Audit event recorded fallback
        self.assertGreaterEqual(len(composite.fallback_history), 1)
        self.assertEqual(composite.fallback_history[0]["primary_model"], "codemind")


if __name__ == "__main__":
    unittest.main()
