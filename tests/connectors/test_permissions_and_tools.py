"""Unit tests for Connector Manifests, Permissions, Risk Tiers, and Tool Schemas."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

from codemind.config import PermissionMode
from codemind.connectors.manager import ConnectorManager
from codemind.connectors.models import (
    ActionRiskLevel,
    AuthMethod,
    ConnectionStatus,
    ConnectorAction,
    ConnectorCredential,
)
from codemind.connectors.permissions import ConnectorPermissionManager, ConnectorPolicy
from codemind.connectors.registry import ConnectorRegistry
from codemind.connectors.tool import ConnectorTool, make_connector_args_schema
from codemind.security.permissions import PermissionChecker
from codemind.security.sandbox import WorkspaceSandbox
from codemind.tools.base import ExecutionContext, ToolResult
from codemind.tools.registry import ToolRegistry


class TestPermissionsAndTools(unittest.TestCase):
    """Hermetic tests for connector permission manager, registry, and tool wrappers."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.temp_dir.name)
        self.manager = ConnectorManager(self.workspace_root)
        self.sandbox = WorkspaceSandbox(self.workspace_root)
        self.permission_checker = PermissionChecker(mode=PermissionMode.TRUSTED, workspace_root=self.workspace_root)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_all_manifests_registered_and_valid(self):
        """Verify all 8 Phase 1 & 2 connectors are registered with valid manifests."""
        expected = ["youtube", "gmail", "google_drive", "google_calendar", "discord", "slack", "notion", "spotify"]
        registered_ids = [m.connector_id for m in self.manager.registry.list_connectors()]

        for exp_id in expected:
            self.assertIn(exp_id, registered_ids)
            manifest = self.manager.registry.get_manifest(exp_id)
            self.assertIsNotNone(manifest)
            self.assertGreater(len(manifest.actions), 0)
            self.assertTrue(manifest.name)
            self.assertTrue(manifest.description)
            self.assertTrue(manifest.category)

    def test_permission_policy_enable_disable(self):
        """Verify disabling a connector prevents any action execution."""
        pm = self.manager.permission_manager
        policy = pm.get_policy("gmail")
        self.assertTrue(policy.enabled)

        # Disable gmail
        policy.enabled = False
        pm.set_policy("gmail", policy)

        allowed, reason = pm.check_permission("gmail", "search_emails", ActionRiskLevel.READ)
        self.assertFalse(allowed)
        self.assertIn("disabled", reason)

    def test_permission_policy_read_only_mode(self):
        """Verify read-only mode permits READ but rejects WRITE and SENSITIVE actions."""
        pm = self.manager.permission_manager
        policy = pm.get_policy("google_drive")
        policy.read_only = True
        pm.set_policy("google_drive", policy)

        # READ action should pass
        allowed_read, _ = pm.check_permission("google_drive", "search_files", ActionRiskLevel.READ)
        self.assertTrue(allowed_read)

        # WRITE action should be blocked
        allowed_write, reason_w = pm.check_permission("google_drive", "create_file", ActionRiskLevel.WRITE)
        self.assertFalse(allowed_write)
        self.assertIn("read-only", reason_w)

        # SENSITIVE action should be blocked
        allowed_sens, reason_s = pm.check_permission("google_drive", "delete_file", ActionRiskLevel.SENSITIVE)
        self.assertFalse(allowed_sens)
        self.assertIn("read-only", reason_s)

    def test_dynamic_pydantic_schema_generation(self):
        """Verify make_connector_args_schema generates a valid Pydantic model for ToolRegistry."""
        json_schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results", "default": 10},
            },
            "required": ["query"],
        }
        ModelCls = make_connector_args_schema("gmail_search_emails", json_schema)
        self.assertTrue(hasattr(ModelCls, "model_validate"))
        self.assertTrue(hasattr(ModelCls, "model_json_schema"))

        # Valid input
        instance = ModelCls.model_validate({"query": "inbox test", "limit": 5})
        self.assertEqual(instance.query, "inbox test")
        self.assertEqual(instance.limit, 5)

        # Missing required field must raise ValueError or ValidationError
        with self.assertRaises((ValueError, Exception)):
            ModelCls.model_validate({})

    def test_sensitive_action_requires_user_approval(self):
        """Verify SENSITIVE actions prompt for approval in supervised mode."""
        action = ConnectorAction(
            name="send_email",
            description="Send an email to a recipient",
            risk_level=ActionRiskLevel.SENSITIVE,
            args_schema={"type": "object", "properties": {"to": {"type": "string"}}, "required": ["to"]},
        )

        mock_adapter = AsyncMock()
        mock_adapter.connector_id = "gmail"
        mock_adapter.execute_action.return_value = ToolResult.success("Email sent.")
        mock_adapter.permission_manager = self.manager.permission_manager

        tool = ConnectorTool(mock_adapter, action)

        # Approval rejected mock
        ctx_rejected = ExecutionContext(
            workspace_root=self.workspace_root,
            sandbox=self.sandbox,
            permission_checker=self.permission_checker,
            ui=AsyncMock(),
        )
        ctx_rejected.ui.request_approval = AsyncMock(return_value=False)

        import asyncio
        res = asyncio.run(tool.execute({"to": "test@example.com"}, ctx_rejected))
        self.assertFalse(res.ok)
        self.assertIn("denied", res.content.lower())
        mock_adapter.execute_action.assert_not_called()

        # Approval granted mock
        ctx_approved = ExecutionContext(
            workspace_root=self.workspace_root,
            sandbox=self.sandbox,
            permission_checker=self.permission_checker,
            ui=AsyncMock(),
        )
        ctx_approved.ui.request_approval = AsyncMock(return_value=True)

        res_ok = asyncio.run(tool.execute({"to": "test@example.com"}, ctx_approved))
        self.assertTrue(res_ok.ok)
        mock_adapter.execute_action.assert_called_once()

    def test_connector_tools_registration_in_agent_tool_registry(self):
        """Verify connected connector tools enter CodeMind central ToolRegistry."""
        # Connect youtube in vault
        self.manager.connect_credential(
            ConnectorCredential(
                connector_id="youtube",
                auth_method=AuthMethod.OAUTH2,
                access_token="test_yt_token",
            )
        )

        agent_tool_registry = ToolRegistry()
        initial_count = len(agent_tool_registry.list_tools())
        # Central registry has default tools
        self.assertGreater(initial_count, 0)

        registered = self.manager.register_tools_with(agent_tool_registry)
        self.assertEqual(registered, 6)
        self.assertEqual(len(agent_tool_registry.list_tools()), initial_count + 6)
        tool_names = [t.name for t in agent_tool_registry.list_tools()]
        self.assertIn("youtube__search_videos", tool_names)
        self.assertIn("youtube__upload_video", tool_names)


if __name__ == "__main__":
    unittest.main()
