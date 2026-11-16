"""Abstract base adapter for all application connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
import time
from typing import Any

from codemind.connectors.auth import ConnectorAuthManager
from codemind.connectors.logger import ConnectorAuditLogger
from codemind.connectors.models import (
    ConnectionStatus,
    ConnectorCredential,
    ConnectorHealth,
    ConnectorManifest,
)
from codemind.connectors.permissions import ConnectorPermissionManager
from codemind.connectors.tool import ConnectorTool
from codemind.connectors.vault import CredentialVault
from codemind.tools.base import BaseTool, ExecutionContext, ToolResult


class ConnectorAdapter(ABC):
    """Abstract base class that all native and third-party application connectors implement."""

    manifest: ConnectorManifest

    def __init__(
        self,
        vault: CredentialVault,
        auth_manager: ConnectorAuthManager | None = None,
        permission_manager: ConnectorPermissionManager | None = None,
        audit_logger: ConnectorAuditLogger | None = None,
    ):
        self.vault = vault
        self.auth_manager = auth_manager or ConnectorAuthManager(self.vault)
        self.permission_manager = permission_manager
        self.audit_logger = audit_logger

    @property
    def connector_id(self) -> str:
        return self.manifest.connector_id

    def is_connected(self) -> bool:
        """Check if active credentials are present in the vault."""
        return self.vault.is_authenticated(self.connector_id)

    def get_status(self) -> ConnectionStatus:
        """Inspect current connection status."""
        cred = self.vault.get_credential(self.connector_id)
        if not cred:
            return ConnectionStatus.DISCONNECTED
        if cred.is_expired:
            return ConnectionStatus.EXPIRED
        return ConnectionStatus.CONNECTED

    def get_tools(self) -> list[BaseTool]:
        """Wrap all declared manifest actions as executable CodeMind tools."""
        tools: list[BaseTool] = []
        for action in self.manifest.actions:
            # Check if action is enabled by policy
            if self.permission_manager:
                policy = self.permission_manager.get_policy(self.connector_id)
                if not policy.enabled or action.name in policy.disabled_actions:
                    continue
            tools.append(ConnectorTool(self, action))
        return tools

    def disconnect(self) -> bool:
        """Remove authorized credentials from the local vault."""
        return self.vault.delete_credential(self.connector_id)

    @abstractmethod
    async def check_health(self) -> ConnectorHealth:
        """Perform provider health and authentication connectivity check."""
        pass

    @abstractmethod
    async def execute_action(
        self,
        action_name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        """Execute the requested connector action against the upstream API."""
        pass
