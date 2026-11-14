"""Unit tests for 'codemind models' CLI subcommands."""

from unittest.mock import AsyncMock, patch
from typer.testing import CliRunner

from codemind.cli.main import app
from codemind.config import CodeMindConfig
from codemind.models.discovery import DiscoveredModel, ModelDiscovery
from tests.base import BaseAgentTestCase


class TestModelsCLI(BaseAgentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.runner = CliRunner()

    def test_models_list_command(self) -> None:
        mock_list = [
            DiscoveredModel(
                name="qwen-mock-test",
                provider="ollama",
                endpoint="http://127.0.0.1:11434",
                parameter_size="14B",
                size_gb=8.5,
                is_active=True,
            )
        ]
        with patch.object(ModelDiscovery, "discover_all", new_callable=AsyncMock) as mock_disc:
            mock_disc.return_value = mock_list
            res = self.runner.invoke(app, ["models", "list", "--plain", "-w", str(self.workspace_root)])
            self.assertEqual(res.exit_code, 0)
            self.assertIn("qwen-mock-test", res.output)
            self.assertIn("[ACTIVE]", res.output)

    def test_models_current_command(self) -> None:
        res = self.runner.invoke(app, ["models", "current", "--plain", "-w", str(self.workspace_root)])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Model:", res.output)
        self.assertIn("Provider:", res.output)

    def test_models_use_command(self) -> None:
        mock_list = [
            DiscoveredModel(
                name="mixtral:latest",
                provider="ollama",
                endpoint="http://127.0.0.1:11434",
            )
        ]
        with patch.object(ModelDiscovery, "discover_all", new_callable=AsyncMock) as mock_disc:
            mock_disc.return_value = mock_list
            res = self.runner.invoke(app, ["models", "use", "mixtral:latest", "--plain", "-w", str(self.workspace_root)])
            self.assertEqual(res.exit_code, 0)
            self.assertIn("Active model set to 'mixtral:latest'", res.output)

        # Verify persisted configuration
        cfg = CodeMindConfig.load(workspace_dir=self.workspace_root)
        self.assertEqual(cfg.model.model_name, "mixtral:latest")
