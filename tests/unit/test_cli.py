"""Unit tests for CLI commands and rendering."""

from typer.testing import CliRunner

from codemind import __version__
from codemind.cli.branding import BRAND_MARK
from codemind.cli.main import app
from tests.base import BaseAgentTestCase


class TestCLI(BaseAgentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.runner = CliRunner()

    def test_version_flag(self) -> None:
        result = self.runner.invoke(app, ["--version"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn(__version__, result.output)
        self.assertIn("CodeMind", result.output)

    def test_help_flag(self) -> None:
        result = self.runner.invoke(app, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("CodeMind", result.output)
        self.assertIn("--resume", result.output)
        self.assertIn("--mode", result.output)
        self.assertIn("--plain", result.output)

    def test_status_command(self) -> None:
        result = self.runner.invoke(app, ["status", "--plain", "-w", str(self.workspace_root)])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Model:", result.output)
        self.assertIn("Workspace:", result.output)

    def test_memory_cli_commands(self) -> None:
        self.create_file("pyproject.toml", "[project]\nname = 'demo'\n")
        self.create_file("src/app.py", "print('hello')\n")
        ws_str = str(self.workspace_root)
        # 1. status
        res = self.runner.invoke(app, ["memory", "status", "--plain", "-w", ws_str])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Persistent Project Memory Status", res.output)

        # 2. rebuild
        res = self.runner.invoke(app, ["memory", "rebuild", "--plain", "-w", ws_str])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Rebuild complete", res.output)

        # 3. show
        res = self.runner.invoke(app, ["memory", "show", "--plain", "-w", ws_str])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Active Project Memory Snapshot", res.output)

        # 4. list
        res = self.runner.invoke(app, ["memory", "list", "--plain", "-w", ws_str])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("mem_proj_identity", res.output)

        # 5. search
        res = self.runner.invoke(app, ["memory", "search", "Python", "--plain", "-w", ws_str])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Search Results for 'Python'", res.output)

        # 6. update
        res = self.runner.invoke(app, ["memory", "update", "mem_proj_identity", "--pin", "--plain", "-w", ws_str])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Successfully updated memory entry", res.output)

        # 7. clear
        res = self.runner.invoke(app, ["memory", "clear", "--force", "--plain", "-w", ws_str])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Purged", res.output)

    def test_task_cli_commands(self) -> None:
        from codemind.orchestration.checkpoint import CheckpointManager, WorkflowCheckpoint
        ws_str = str(self.workspace_root)
        mgr = CheckpointManager(self.workspace_root)

        # Save a test checkpoint
        ckpt = WorkflowCheckpoint(
            session_id="cm-test-session",
            workspace_root=ws_str,
            instruction="Implement feature X and tests",
            current_task_id="task-1",
            tasks=[
                {"id": "task-1", "title": "Implement core X", "status": "completed", "evidence": "X created"},
                {"id": "task-2", "title": "Author tests", "status": "pending", "dependencies": ["task-1"]},
            ],
            completed_task_ids=["task-1"],
            pending_task_ids=["task-2"],
            files_created=["src/x.py"],
        )
        mgr.save_checkpoint_atomic(ckpt)

        # 1. status
        res = self.runner.invoke(app, ["task", "status", "-w", ws_str])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("task-1", res.output)
        self.assertIn("task-2", res.output)

        # 2. inspect
        res = self.runner.invoke(app, ["task", "inspect", "task-1", "-w", ws_str])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Task Node: task-1", res.output)
        self.assertIn("Implement core X", res.output)

        # 3. history
        res = self.runner.invoke(app, ["task", "history", "-w", ws_str])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("cm-test", res.output)

        # 4. pause
        res = self.runner.invoke(app, ["task", "pause", "cm-test-session", "-w", ws_str])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("safely paused", res.output)

        # 5. resume
        res = self.runner.invoke(app, ["task", "resume", "cm-test-session", "-w", ws_str])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Ready to resume", res.output)

        # 6. cancel
        res = self.runner.invoke(app, ["task", "cancel", "cm-test-session", "-w", ws_str])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("cancelled", res.output)

    def test_agents_and_sidecar_cli_integration(self) -> None:
        ws_str = str(self.workspace_root)
        # 1. agents list
        res_agents = self.runner.invoke(app, ["agents", "list", "-w", ws_str])
        self.assertEqual(res_agents.exit_code, 0)
        self.assertIn("research", res_agents.output)

        # 2. agents status
        res_astat = self.runner.invoke(app, ["agents", "status", "-w", ws_str])
        self.assertEqual(res_astat.exit_code, 0)
        self.assertIn("Runtime State", res_astat.output)

        # 3. sidecar status
        res_scstat = self.runner.invoke(app, ["sidecar", "status", "-w", ws_str])
        self.assertEqual(res_scstat.exit_code, 0)
        self.assertIn("Runtime Status", res_scstat.output)

        # 4. sidecar start
        res_scstart = self.runner.invoke(app, ["sidecar", "start", "-w", ws_str])
        self.assertEqual(res_scstart.exit_code, 0)
        self.assertIn("initialized", res_scstart.output)
