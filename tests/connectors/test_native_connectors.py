"""Hermetic mocked API tests for all Phase 1 and Phase 2 Native Connectors."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from codemind.config import PermissionMode
from codemind.connectors.manager import ConnectorManager
from codemind.connectors.models import (
    ActionRiskLevel,
    AuthMethod,
    ConnectionStatus,
    ConnectorCredential,
)
from codemind.security.permissions import PermissionChecker
from codemind.security.sandbox import WorkspaceSandbox
from codemind.tools.base import ExecutionContext, ToolResult


class TestNativeConnectors(unittest.TestCase):
    """Verify behavior of all native adapters against mocked HTTP endpoints."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.temp_dir.name)
        self.manager = ConnectorManager(self.workspace_root)
        self.sandbox = WorkspaceSandbox(self.workspace_root)
        self.permission_checker = PermissionChecker(mode=PermissionMode.TRUSTED, workspace_root=self.workspace_root)
        self.context = ExecutionContext(
            workspace_root=self.workspace_root,
            sandbox=self.sandbox,
            permission_checker=self.permission_checker,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _setup_cred(self, connector_id: str, auth_method: AuthMethod = AuthMethod.OAUTH2):
        self.manager.connect_credential(
            ConnectorCredential(
                connector_id=connector_id,
                auth_method=auth_method,
                access_token="mock_valid_token_xyz",
            )
        )

    # 1. GMAIL
    @patch("httpx.AsyncClient.get")
    def test_gmail_search_emails(self, mock_get):
        self._setup_cred("gmail")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "messages": [{"id": "m1", "threadId": "t1"}, {"id": "m2", "threadId": "t2"}]
        }
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp

        adapter = self.manager.get_adapter("gmail")
        res = asyncio.run(adapter.execute_action("search_emails", {"query": "invoice"}, self.context))
        self.assertTrue(res.ok)
        self.assertIn("Found 2 email(s)", res.content)

    # 2. GOOGLE DRIVE
    @patch("httpx.AsyncClient.get")
    def test_drive_search_files(self, mock_get):
        self._setup_cred("google_drive")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "files": [
                {"id": "f1", "name": "Project Roadmap.docx", "mimeType": "application/vnd.google-apps.document"},
                {"id": "f2", "name": "Budget.xlsx", "mimeType": "application/vnd.google-apps.spreadsheet"},
            ]
        }
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp

        adapter = self.manager.get_adapter("google_drive")
        res = asyncio.run(adapter.execute_action("search_files", {"query": "name contains 'Roadmap'"}, self.context))
        self.assertTrue(res.ok)
        self.assertIn("Project Roadmap.docx", res.content)

    # 3. GOOGLE CALENDAR
    @patch("httpx.AsyncClient.get")
    def test_calendar_list_events(self, mock_get):
        self._setup_cred("google_calendar")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "id": "ev1",
                    "summary": "Sprint Planning",
                    "start": {"dateTime": "2026-11-17T10:00:00Z"},
                    "end": {"dateTime": "2026-11-17T11:00:00Z"},
                }
            ]
        }
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp

        adapter = self.manager.get_adapter("google_calendar")
        res = asyncio.run(adapter.execute_action("list_events", {"max_results": 5}, self.context))
        self.assertTrue(res.ok)
        self.assertIn("Sprint Planning", res.content)

    # 4. YOUTUBE
    @patch("httpx.AsyncClient.get")
    def test_youtube_search_videos(self, mock_get):
        self._setup_cred("youtube")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "id": {"videoId": "vid123"},
                    "snippet": {
                        "title": "Autonomous AI Agent Tutorial",
                        "channelTitle": "CodeMind Dev",
                        "publishedAt": "2026-01-01T00:00:00Z",
                    },
                }
            ]
        }
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp

        adapter = self.manager.get_adapter("youtube")
        res = asyncio.run(adapter.execute_action("search_videos", {"query": "AI tutorial"}, self.context))
        self.assertTrue(res.ok)
        self.assertIn("Autonomous AI Agent Tutorial", res.content)

    # 5. DISCORD
    @patch("httpx.AsyncClient.get")
    def test_discord_read_channel(self, mock_get):
        self._setup_cred("discord", AuthMethod.BOT_TOKEN)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": "msg1", "author": {"username": "Alice"}, "content": "Hello team!", "timestamp": "2026-11-16T12:00:00Z"}
        ]
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp

        adapter = self.manager.get_adapter("discord")
        res = asyncio.run(adapter.execute_action("read_channel", {"channel_id": "12345678"}, self.context))
        self.assertTrue(res.ok)
        self.assertIn("Alice: Hello team!", res.content)

    # 6. SLACK
    @patch("httpx.AsyncClient.get")
    def test_slack_list_channels(self, mock_get):
        self._setup_cred("slack", AuthMethod.BOT_TOKEN)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "channels": [{"id": "C123", "name": "general", "is_private": False, "num_members": 42}],
        }
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp

        adapter = self.manager.get_adapter("slack")
        res = asyncio.run(adapter.execute_action("list_channels", {}, self.context))
        self.assertTrue(res.ok)
        self.assertIn("#general", res.content)

    # 7. NOTION
    @patch("httpx.AsyncClient.post")
    def test_notion_search_pages(self, mock_post):
        self._setup_cred("notion", AuthMethod.API_KEY)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "id": "page-999",
                    "object": "page",
                    "url": "https://notion.so/page-999",
                    "last_edited_time": "2026-11-16T10:00:00Z",
                    "properties": {
                        "title": {"type": "title", "title": [{"plain_text": "Engineering Roadmap"}]}
                    },
                }
            ]
        }
        mock_resp.raise_for_status = lambda: None
        mock_post.return_value = mock_resp

        adapter = self.manager.get_adapter("notion")
        res = asyncio.run(adapter.execute_action("search_pages", {"query": "Roadmap"}, self.context))
        self.assertTrue(res.ok)
        self.assertIn("Engineering Roadmap", res.content)

    # 8. SPOTIFY
    @patch("httpx.AsyncClient.get")
    def test_spotify_search(self, mock_get):
        self._setup_cred("spotify")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tracks": {
                "items": [
                    {
                        "id": "trk1",
                        "name": "Midnight Coding",
                        "artists": [{"name": "SynthWave Dev"}],
                        "album": {"name": "Lo-Fi Beats"},
                        "uri": "spotify:track:trk1",
                        "duration_ms": 180000,
                    }
                ]
            }
        }
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp

        adapter = self.manager.get_adapter("spotify")
        res = asyncio.run(adapter.execute_action("search", {"query": "coding"}, self.context))
        self.assertTrue(res.ok)
        self.assertIn("Midnight Coding", res.content)

    # FALSE-SUCCESS PREVENTION & ERROR HANDLING
    @patch("httpx.AsyncClient.get")
    def test_false_success_prevention_on_api_error(self, mock_get):
        """Verify 401/403/500 API responses return ToolResult.error and never report success."""
        self._setup_cred("gmail")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = '{"error": {"code": 401, "message": "Invalid Credentials"}}'

        # Simulate raise_for_status raising HTTPStatusError
        req = httpx.Request("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages")
        err = httpx.HTTPStatusError("401 Unauthorized", request=req, response=httpx.Response(401, text=mock_resp.text, request=req))
        mock_get.side_effect = err

        adapter = self.manager.get_adapter("gmail")
        res = asyncio.run(adapter.execute_action("search_emails", {"query": "test"}, self.context))
        self.assertFalse(res.ok)
        self.assertIn("401", res.content)


if __name__ == "__main__":
    unittest.main()
