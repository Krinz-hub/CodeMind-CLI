"""Unit and integration tests for Connectors and MCP CLI suites."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from typer.testing import CliRunner

from codemind.cli.main import app
from codemind.connectors.manager import ConnectorManager
from codemind.connectors.models import AuthMethod, ConnectorCredential


class TestConnectorsCLI(unittest.TestCase):
    """Hermetic tests for 'codemind connectors' and 'codemind mcp' CLI commands."""

    def setUp(self):
        self.runner = CliRunner()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_connectors_list_cmd(self):
        """Verify 'codemind connectors list' lists all built-in connectors."""
        res = self.runner.invoke(app, ["connectors", "list", "--plain", "-w", str(self.workspace_root)])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("YouTube", res.output)
        self.assertIn("Gmail", res.output)
        self.assertIn("Google Drive", res.output)
        self.assertIn("Google Calendar", res.output)
        self.assertIn("Discord", res.output)
        self.assertIn("Slack", res.output)
        self.assertIn("Notion", res.output)
        self.assertIn("Spotify", res.output)

    def test_connectors_search_cmd(self):
        """Verify 'codemind connectors search' locates matching connectors."""
        res = self.runner.invoke(app, ["connectors", "search", "youtube", "--plain", "-w", str(self.workspace_root)])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("youtube", res.output)

    def test_connectors_inspect_cmd(self):
        """Verify 'codemind connectors inspect' displays full manifest and actions."""
        res = self.runner.invoke(app, ["connectors", "inspect", "gmail", "--plain", "-w", str(self.workspace_root)])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Gmail", res.output)
        self.assertIn("search_emails", res.output)
        self.assertIn("send_email", res.output)
        self.assertIn("SENSITIVE", res.output)

    def test_connectors_connect_and_disconnect_cmd(self):
        """Verify connecting and disconnecting updates the encrypted vault."""
        # Connect with token flag
        res_conn = self.runner.invoke(
            app,
            ["connectors", "connect", "slack", "--token", "xoxb-test-bot-token", "--plain", "-w", str(self.workspace_root)],
        )
        self.assertEqual(res_conn.exit_code, 0)
        self.assertIn("securely encrypted", res_conn.output)

        # Inspect status
        res_status = self.runner.invoke(app, ["connectors", "status", "--plain", "-w", str(self.workspace_root)])
        self.assertEqual(res_status.exit_code, 0)
        self.assertIn("slack", res_status.output)

        # Disconnect with --force
        res_disc = self.runner.invoke(
            app,
            ["connectors", "disconnect", "slack", "--force", "--plain", "-w", str(self.workspace_root)],
        )
        self.assertEqual(res_disc.exit_code, 0)
        self.assertIn("disconnected", res_disc.output)

    def test_connectors_permissions_cmd(self):
        """Verify configuring permission policy via CLI."""
        res_ro = self.runner.invoke(
            app,
            ["connectors", "permissions", "google_drive", "--read-only", "--plain", "-w", str(self.workspace_root)],
        )
        self.assertEqual(res_ro.exit_code, 0)
        self.assertIn("Read-Only Mode: True", res_ro.output)

    def test_connectors_tools_cmd(self):
        """Verify 'codemind connectors tools' lists all tools exposed by the connector."""
        res = self.runner.invoke(app, ["connectors", "tools", "spotify", "--plain", "-w", str(self.workspace_root)])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("spotify__search", res.output)
        self.assertIn("spotify__playback_control", res.output)

    def test_mcp_cli_lifecycle(self):
        """Verify 'codemind mcp add', 'list', 'inspect', and 'remove' commands."""
        ws = str(self.workspace_root)

        # 1. Add server
        res_add = self.runner.invoke(app, ["mcp", "add", "sqlite-srv", "python", "-a", "-m", "-a", "sqlite_mcp", "-w", ws])
        self.assertEqual(res_add.exit_code, 0)
        self.assertIn("registered", res_add.output)

        # 2. List servers
        res_list = self.runner.invoke(app, ["mcp", "list", "--plain", "-w", ws])
        self.assertEqual(res_list.exit_code, 0)
        self.assertIn("sqlite-srv", res_list.output)

        # 3. Inspect server
        res_insp = self.runner.invoke(app, ["mcp", "inspect", "sqlite-srv", "--plain", "-w", ws])
        self.assertEqual(res_insp.exit_code, 0)
        self.assertIn("sqlite-srv", res_insp.output)

        # 4. Remove server
        res_rm = self.runner.invoke(app, ["mcp", "remove", "sqlite-srv", "-w", ws])
        self.assertEqual(res_rm.exit_code, 0)
        self.assertIn("removed", res_rm.output)


if __name__ == "__main__":
    unittest.main()
