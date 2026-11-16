"""Data models and configurations for the Model Context Protocol (MCP) integration."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class MCPTransportType(str, Enum):
    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


class MCPServerConfig(BaseModel):
    """Configuration for an individual MCP server (supporting stdio and streamable HTTP/SSE)."""

    name: str
    transport: MCPTransportType = MCPTransportType.STDIO
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None
    disabled: bool = False
    timeout_seconds: int = 30
    max_reconnect_attempts: int = 3


class MCPToolDefinition(BaseModel):
    """Definition of an MCP tool exposed by a server."""

    name: str
    description: str = ""
    inputSchema: dict[str, Any] = Field(default_factory=dict)


class MCPServersConfig(BaseModel):
    """Configuration envelope stored in .codemind/mcp.json."""

    mcpServers: dict[str, MCPServerConfig] = Field(default_factory=dict)
