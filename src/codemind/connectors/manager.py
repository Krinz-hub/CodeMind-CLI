"""High-level connector manager coordinating registry, vault, adapters, and tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codemind.connectors.auth import ConnectorAuthManager
from codemind.connectors.base import ConnectorAdapter
from codemind.connectors.logger import ConnectorAuditLogger
from codemind.connectors.models import (
    ConnectionStatus,
    ConnectorCredential,
    ConnectorHealth,
    ConnectorManifest,
)
from codemind.connectors.permissions import ConnectorPermissionManager
from codemind.connectors.registry import ConnectorRegistry
from codemind.connectors.vault import CredentialVault
from codemind.tools.base import BaseTool
from codemind.tools.registry import ToolRegistry


class ConnectorManager:
    """Universal gateway orchestrating external application connectors."""

    def __init__(self, workspace_root: Path, vault: CredentialVault | None = None):
        self.workspace_root = workspace_root.resolve()
        self.vault = vault or CredentialVault(
            db_path=self.workspace_root / ".codemind" / "vault.db",
            key_file=self.workspace_root / ".codemind" / ".vault_key",
        )
        self.auth_manager = ConnectorAuthManager(self.vault)
        self.permission_manager = ConnectorPermissionManager(self.workspace_root)
        self.audit_logger = ConnectorAuditLogger(
            self.workspace_root / ".codemind" / "connectors" / "audit.jsonl"
        )
        self.registry = ConnectorRegistry()
        self._instances: dict[str, ConnectorAdapter] = {}

        self._register_default_connectors()

    def _register_default_connectors(self) -> None:
        """Register all built-in Phase 1 and Phase 2 native application connectors."""
        # Native connectors will be registered here
        try:
            from codemind.connectors.native.youtube import YouTubeConnector
            self.registry.register(YouTubeConnector)
        except ImportError:
            pass

        try:
            from codemind.connectors.native.gmail import GmailConnector
            self.registry.register(GmailConnector)
        except ImportError:
            pass

        try:
            from codemind.connectors.native.google_drive import GoogleDriveConnector
            self.registry.register(GoogleDriveConnector)
        except ImportError:
            pass

        try:
            from codemind.connectors.native.google_calendar import GoogleCalendarConnector
            self.registry.register(GoogleCalendarConnector)
        except ImportError:
            pass

        try:
            from codemind.connectors.native.discord import DiscordConnector
            self.registry.register(DiscordConnector)
        except ImportError:
            pass

        try:
            from codemind.connectors.native.slack import SlackConnector
            self.registry.register(SlackConnector)
        except ImportError:
            pass

        try:
            from codemind.connectors.native.notion import NotionConnector
            self.registry.register(NotionConnector)
        except ImportError:
            pass

        try:
            from codemind.connectors.native.spotify import SpotifyConnector
            self.registry.register(SpotifyConnector)
        except ImportError:
            pass

    def get_adapter(self, connector_id: str) -> ConnectorAdapter | None:
        """Instantiate or retrieve cached adapter for a connector."""
        if connector_id in self._instances:
            return self._instances[connector_id]

        cls = self.registry.get(connector_id)
        if not cls:
            return None

        adapter = cls(
            vault=self.vault,
            auth_manager=self.auth_manager,
            permission_manager=self.permission_manager,
            audit_logger=self.audit_logger,
        )
        self._instances[connector_id] = adapter
        return adapter

    def get_active_tools(self) -> list[BaseTool]:
        """Collect all executable tools from currently connected connectors."""
        tools: list[BaseTool] = []
        for manifest in self.registry.list_connectors():
            adapter = self.get_adapter(manifest.connector_id)
            if adapter and adapter.is_connected():
                tools.extend(adapter.get_tools())
        return tools

    def register_tools_with(self, tool_registry: ToolRegistry) -> int:
        """Register all tools from connected connectors into CodeMind's central ToolRegistry."""
        active_tools = self.get_active_tools()
        for tool in active_tools:
            tool_registry.register(tool)
        return len(active_tools)

    def connect_credential(self, cred: ConnectorCredential) -> None:
        """Store new or updated credentials in vault."""
        self.vault.store_credential(cred)

    def disconnect(self, connector_id: str) -> bool:
        """Disconnect connector by removing its credentials."""
        adapter = self.get_adapter(connector_id)
        if adapter:
            return adapter.disconnect()
        return self.vault.delete_credential(connector_id)

    async def test_connection(self, connector_id: str) -> ConnectorHealth:
        """Perform health and authentication verification for a connector."""
        adapter = self.get_adapter(connector_id)
        if not adapter:
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.DISCONNECTED,
                message=f"Connector '{connector_id}' is not installed or registered.",
            )
        return await adapter.check_health()

    def get_all_statuses(self) -> list[dict[str, Any]]:
        """Inspect status across all registered catalogue connectors."""
        statuses: list[dict[str, Any]] = []
        for m in self.registry.list_connectors():
            adapter = self.get_adapter(m.connector_id)
            status = adapter.get_status() if adapter else ConnectionStatus.DISCONNECTED
            policy = self.permission_manager.get_policy(m.connector_id)
            statuses.append({
                "connector_id": m.connector_id,
                "name": m.name,
                "icon": m.icon,
                "category": m.category,
                "status": status.value,
                "is_connected": (status == ConnectionStatus.CONNECTED),
                "is_enabled": policy.enabled,
                "read_only": policy.read_only,
                "actions_count": len(m.actions),
            })
        return statuses
