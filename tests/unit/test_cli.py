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
