"""CodeMind Model Context Protocol (MCP) integration module (Phase D Workstream I)."""

from codemind.mcp.client import MCPClient, MCPClientError
from codemind.mcp.manager import MCPManager
from codemind.mcp.models import MCPServerConfig, MCPServersConfig, MCPToolDefinition
from codemind.mcp.tool import MCPProxyTool, make_mcp_args_schema

__all__ = [
    "MCPClient",
    "MCPClientError",
    "MCPManager",
    "MCPServerConfig",
    "MCPServersConfig",
    "MCPToolDefinition",
    "MCPProxyTool",
    "make_mcp_args_schema",
]
