"""Data models, manifests, and contracts for the Universal Connector Ecosystem."""

from __future__ import annotations

from enum import Enum
import time
from typing import Any

from pydantic import BaseModel, Field


class ActionRiskLevel(str, Enum):
    """Risk classification of connector actions."""
    READ = "read"          # Search, inspect, list metadata (auto-allowed in supervised mode)
    WRITE = "write"        # Create files, update records, modify playlists
    SENSITIVE = "sensitive"  # Send emails, publish videos, delete resources, post messages


class AuthMethod(str, Enum):
    """Authentication mechanism utilized by the connector."""
    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    BOT_TOKEN = "bot_token"
    NONE = "none"


class ConnectionStatus(str, Enum):
    """Connection and health status of an integrated connector."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    EXPIRED = "expired"
    ERROR = "error"
    CONFIGURING = "configuring"


class ConnectorAction(BaseModel):
    """Definition of an individual capability/tool exposed by a connector."""

    name: str
    description: str
    risk_level: ActionRiskLevel = ActionRiskLevel.READ
    args_schema: dict[str, Any] = Field(default_factory=dict)
    required_scopes: list[str] = Field(default_factory=list)


class ConnectorManifest(BaseModel):
    """Immutable metadata and schema declaration for a connector."""

    connector_id: str
    name: str
    description: str
    category: str  # e.g., communication, storage, productivity, media
    version: str = "1.0.0"
    icon: str = "🔌"
    auth_method: AuthMethod = AuthMethod.OAUTH2
    required_scopes: list[str] = Field(default_factory=list)
    optional_scopes: list[str] = Field(default_factory=list)
    actions: list[ConnectorAction] = Field(default_factory=list)
    config_schema: dict[str, Any] = Field(default_factory=dict)
    doc_url: str = ""


class ConnectorHealth(BaseModel):
    """Health check outcome for an active or configured connector."""

    healthy: bool
    status: ConnectionStatus
    message: str
    latency_ms: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)


class ConnectorCredential(BaseModel):
    """Secure credential bundle for an authorized connector."""

    connector_id: str
    auth_method: AuthMethod = AuthMethod.OAUTH2
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "Bearer"
    api_key: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    scopes: list[str] = Field(default_factory=list)
    expires_at: float | None = None  # epoch timestamp seconds
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 60-second buffer)."""
        if self.expires_at is None:
            return False
        return time.time() >= (self.expires_at - 60.0)
