"""Unit tests for Global Launcher, Doctor diagnostics, and Service Manager."""

import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from codemind.cli.doctor import (
    check_cli_launcher,
    check_dependencies,
    check_local_model_services,
    check_python_environment,
    check_workspace_and_tools,
    run_doctor,
)
from codemind.cli.install_cmd import run_install
from codemind.cli.main import app
from codemind.config import CodeMindConfig, ModelProvider, ModelSettings
from codemind.launcher import (
    check_missing_dependencies,
    find_codemind_venv,
    is_running_in_target_venv,
)
from codemind.models.service_manager import (
    check_provider_availability,
    ensure_model_service,
    is_ollama_running,
    start_ollama_server,
)
from tests.base import BaseAgentTestCase


class TestLauncherAndDoctor(BaseAgentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.runner = CliRunner()

    def test_find_codemind_venv_discovery(self) -> None:
        """Verify venv discovery hierarchy finds repo .venv or env override."""
        # 1. Env override
        fake_venv = self.workspace_root / "fake_env_venv"
        (fake_venv / "bin").mkdir(parents=True)
        (fake_venv / "bin" / "python").touch()

        with patch.dict(os.environ, {"CODEMIND_VENV": str(fake_venv)}):
            found = find_codemind_venv()
            self.assertEqual(found, fake_venv)

        # 2. Repo .venv
        with patch.dict(os.environ, {}, clear=False):
            if "CODEMIND_VENV" in os.environ:
                del os.environ["CODEMIND_VENV"]
            found = find_codemind_venv()
            self.assertIsNotNone(found)
            self.assertTrue(found.is_dir())

    def test_is_running_in_target_venv(self) -> None:
        """Verify target venv detection with environment flags and prefixes."""
        with patch.dict(os.environ, {"CODEMIND_VENV_ACTIVE": "1"}):
            self.assertTrue(is_running_in_target_venv(Path("/tmp/any_venv")))

        with patch.dict(os.environ, {"CODEMIND_VENV_ACTIVE": "0"}):
            # Same prefix
            self.assertTrue(is_running_in_target_venv(Path(sys.prefix)))
            # Different prefix
            self.assertFalse(is_running_in_target_venv(Path("/nonexistent/other/venv")))

    def test_check_missing_dependencies(self) -> None:
        """Verify check_missing_dependencies returns empty when all are installed."""
        missing = check_missing_dependencies()
        self.assertEqual(missing, [])

    def test_doctor_diagnostics_suite(self) -> None:
        """Verify doctor individual diagnostic checks."""
        # Python check
        py_results = check_python_environment()
        self.assertTrue(any(r.name == "Python Version" and r.status == "PASS" for r in py_results))

        # Dependencies check
        dep_results = check_dependencies()
        self.assertTrue(all(r.status == "PASS" for r in dep_results))

        # CLI launcher check
        cli_results = check_cli_launcher()
        self.assertTrue(any(r.name == "Global Command" for r in cli_results))

        # Workspace check
        ws_results = check_workspace_and_tools(self.workspace_root)
        self.assertTrue(any(r.name == "Workspace Directory" and r.status == "PASS" for r in ws_results))

    def test_doctor_cli_command(self) -> None:
        """Verify 'codemind doctor' executes with exit code 0."""
        res = self.runner.invoke(app, ["doctor", "--plain", "-w", str(self.workspace_root)])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("CodeMind Doctor Diagnostics", res.output)
        self.assertIn("Python Environment", res.output)
        self.assertIn("Dependencies", res.output)
        self.assertIn("Summary:", res.output)

    def test_service_manager_mock_provider(self) -> None:
        """Verify mock provider availability is always ready."""
        import asyncio

        mock_cfg = ModelSettings(provider=ModelProvider.MOCK, model_name="mock-model")
        ok, msg, details = asyncio.run(check_provider_availability(mock_cfg))
        self.assertTrue(ok)
        self.assertEqual(details.get("provider"), "mock")

    def test_service_manager_unreachable_endpoint(self) -> None:
        """Verify unreachable endpoint returns failure and clear message."""
        import asyncio

        bad_cfg = ModelSettings(
            provider=ModelProvider.OLLAMA,
            model_name="qwen3.6:35b",
            endpoint="http://127.0.0.1:59999",
        )
        ok, msg, details = asyncio.run(check_provider_availability(bad_cfg))
        self.assertFalse(ok)
        self.assertIn("unreachable", msg.lower())

    def test_install_cli_command(self) -> None:
        """Verify 'codemind install' creates launcher in target bin dir."""
        test_bin = self.workspace_root / "test_bin"
        test_venv = self.workspace_root / "test_venv"
        (test_venv / "bin").mkdir(parents=True)
        (test_venv / "bin" / "python").touch()
        (test_venv / "bin" / "pip").touch()
        (test_venv / "bin" / "codemind").touch()

        with patch("subprocess.run") as mock_subproc:
            mock_subproc.return_value = MagicMock(returncode=0)
            res = self.runner.invoke(
                app,
                ["install", "--plain", "--bin-dir", str(test_bin), "--venv", str(test_venv)],
            )
            self.assertEqual(res.exit_code, 0)
            # Verify launcher was created
            self.assertTrue((test_bin / "codemind").is_file() or (test_bin / "codemind").is_symlink())


if __name__ == "__main__":
    unittest.main()
