"""MCP configuration lifecycle and registry manager (Phase D Workstream I)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codemind.mcp.client import MCPClient, MCPClientError
from codemind.mcp.models import MCPServerConfig, MCPServersConfig, MCPTransportType
from codemind.mcp.tool import MCPProxyTool
from codemind.tools.registry import ToolRegistry


class MCPManager:
    """Discovers, initializes, and manages MCP servers and their proxy tools."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.config_dir = self.workspace_root / ".codemind"
        self.config_file = self.config_dir / "mcp.json"
        self._active_clients: dict[str, MCPClient] = {}
        self._active_tools: dict[str, list[MCPProxyTool]] = {}

    def load_config(self) -> MCPServersConfig:
        """Load configured MCP servers from .codemind/mcp.json."""
        if not self.config_file.is_file():
            return MCPServersConfig()

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return MCPServersConfig.model_validate(data)
        except Exception:
            return MCPServersConfig()

    def save_config(self, config: MCPServersConfig) -> None:
        """Persist MCP server configuration to .codemind/mcp.json."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config.model_dump(), f, indent=2)

    def add_server(
        self,
        name: str,
        command: str | None = None,
        args: list[str] | None = None,
        transport: str = "stdio",
        url: str | None = None,
        headers: dict[str, str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        disabled: bool = False,
    ) -> MCPServerConfig:
        """Register or update an MCP server configuration."""
        config = self.load_config()
        t_type = MCPTransportType(transport.lower()) if transport else MCPTransportType.STDIO
        server = MCPServerConfig(
            name=name,
            transport=t_type,
            command=command,
            args=args or [],
            url=url,
            headers=headers or {},
            env=env or {},
            cwd=cwd or str(self.workspace_root),
            disabled=disabled,
        )
        config.mcpServers[name] = server
        self.save_config(config)
        return server

    def remove_server(self, name: str) -> bool:
        """Remove a configured MCP server."""
        config = self.load_config()
        if name in config.mcpServers:
            del config.mcpServers[name]
            self.save_config(config)
            return True
        return False

    def disable_server(self, name: str) -> bool:
        """Mark an MCP server as disabled without deleting its configuration."""
        config = self.load_config()
        if name in config.mcpServers:
            config.mcpServers[name].disabled = True
            self.save_config(config)
            return True
        return False

    def enable_server(self, name: str) -> bool:
        """Re-enable a previously disabled MCP server."""
        config = self.load_config()
        if name in config.mcpServers:
            config.mcpServers[name].disabled = False
            self.save_config(config)
            return True
        return False

    def list_servers(self) -> list[dict[str, Any]]:
        """List all configured servers and their current status."""
        config = self.load_config()
        results: list[dict[str, Any]] = []

        for name, s in config.mcpServers.items():
            client = self._active_clients.get(name)
            tools = self._active_tools.get(name, [])
            results.append({
                "name": name,
                "transport": s.transport.value,
                "command": s.command,
                "url": s.url,
                "args": s.args,
                "disabled": s.disabled,
                "is_running": client.is_running if client else False,
                "tool_count": len(tools),
                "tools": [t.original_tool_name for t in tools],
            })
        return results

    async def test_server(self, name: str) -> dict[str, Any]:
        """Test health, connectivity, and tool discovery of a configured MCP server."""
        config = self.load_config()
        if name not in config.mcpServers:
            return {"healthy": False, "error": f"Server '{name}' is not configured in mcp.json"}

        server_cfg = config.mcpServers[name]
        client = MCPClient(server_cfg)
        try:
            await client.start()
            health = await client.check_health()
            tools = await client.list_tools()
            await client.close()
            return {
                "healthy": health.get("healthy", True),
                "server": name,
                "transport": server_cfg.transport.value,
                "tool_count": len(tools),
                "tools": [t.name for t in tools],
                "error": health.get("error"),
            }
        except Exception as ex:
            await client.close()
            return {
                "healthy": False,
                "server": name,
                "error": str(ex),
            }

    async def initialize_servers(
        self,
        registry: ToolRegistry | None = None,
    ) -> list[MCPProxyTool]:
        """Start enabled MCP servers, discover their tools, and register them."""
        config = self.load_config()
        discovered_tools: list[MCPProxyTool] = []

        for name, s in config.mcpServers.items():
            if s.disabled:
                continue

            client = MCPClient(s)
            try:
                await client.start()
                raw_tools = await client.list_tools()
                server_proxy_tools: list[MCPProxyTool] = []

                for t_def in raw_tools:
                    proxy = MCPProxyTool(server_name=name, tool_def=t_def, client=client)
                    server_proxy_tools.append(proxy)
                    discovered_tools.append(proxy)
                    if registry:
                        registry.register(proxy)

                self._active_clients[name] = client
                self._active_tools[name] = server_proxy_tools

            except Exception as ex:
                # Server startup failure must never crash the CodeMind agent
                await client.close()

        return discovered_tools

    async def shutdown_all(self) -> None:
        """Cleanly close all active MCP client processes."""
        for client in self._active_clients.values():
            try:
                await client.close()
            except Exception:
                pass
        self._active_clients.clear()
        self._active_tools.clear()
