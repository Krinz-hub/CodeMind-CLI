"""Unified stdio and streamable HTTP/SSE client for Model Context Protocol (MCP).

Supports:
- Local stdio transport via subprocess
- Streamable HTTP/SSE transport via httpx
- Automatic reconnection policies
- Sanitization of untrusted tool content
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
import httpx

from codemind.mcp.models import MCPServerConfig, MCPToolDefinition, MCPTransportType
from codemind.security.redaction import redact_secrets


class MCPClientError(Exception):
    """Base exception for MCP client failures."""
    pass


class MCPClient:
    """Manages an active stdio or HTTP/SSE connection to an external MCP server."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.process: asyncio.subprocess.Process | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._post_endpoint: str | None = None
        self._request_id = 0
        self._is_initialized = False
        self._lock = asyncio.Lock()
        self._reconnect_attempts = 0

    @property
    def is_running(self) -> bool:
        if self.config.transport == MCPTransportType.STDIO:
            return self.process is not None and self.process.returncode is None
        return self._is_initialized and self._http_client is not None

    async def start(self) -> None:
        """Initialize connection over the configured transport (stdio or HTTP/SSE)."""
        if self.is_running:
            return

        if self.config.transport == MCPTransportType.STDIO:
            await self._start_stdio()
        else:
            await self._start_http()

    async def _start_stdio(self) -> None:
        """Spawn the MCP server process over stdio."""
        if not self.config.command:
            raise MCPClientError(f"Server '{self.config.name}' requires 'command' for stdio transport.")

        env = dict(os.environ)
        if self.config.env:
            env.update(self.config.env)

        try:
            self.process = await asyncio.create_subprocess_exec(
                self.config.command,
                *self.config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.config.cwd,
                env=env,
            )
        except Exception as ex:
            raise MCPClientError(
                f"Failed to start MCP server '{self.config.name}' ({self.config.command}): {ex}"
            ) from ex

        # Perform initialize handshake
        try:
            await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "CodeMind-CLI", "version": "0.1.0"},
                },
                timeout=self.config.timeout_seconds,
            )
            await self._send_notification("notifications/initialized", {})
            self._is_initialized = True
            self._reconnect_attempts = 0
        except Exception as ex:
            await self.close()
            raise MCPClientError(
                f"MCP initialize handshake failed for '{self.config.name}': {ex}"
            ) from ex

    async def _start_http(self) -> None:
        """Initialize connection over streamable HTTP / SSE."""
        if not self.config.url:
            raise MCPClientError(f"Server '{self.config.name}' requires 'url' for HTTP/SSE transport.")

        self._http_client = httpx.AsyncClient(
            headers=self.config.headers,
            timeout=float(self.config.timeout_seconds),
        )
        self._post_endpoint = self.config.url

        try:
            init_res = await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "CodeMind-CLI", "version": "0.1.0"},
                },
                timeout=self.config.timeout_seconds,
            )
            await self._send_notification("notifications/initialized", {})
            self._is_initialized = True
            self._reconnect_attempts = 0
        except Exception as ex:
            await self.close()
            raise MCPClientError(
                f"MCP HTTP/SSE initialize handshake failed for '{self.config.name}': {ex}"
            ) from ex

    async def list_tools(self) -> list[MCPToolDefinition]:
        """Query the MCP server for available tools via tools/list."""
        if not self._is_initialized:
            await self.start()

        res = await self._send_request("tools/list", {}, timeout=self.config.timeout_seconds)
        raw_tools = res.get("tools", [])
        tools: list[MCPToolDefinition] = []

        for item in raw_tools:
            if isinstance(item, dict) and "name" in item:
                # Treat description as untrusted data - sanitize secrets
                clean_desc = redact_secrets(item.get("description", ""))
                tools.append(
                    MCPToolDefinition(
                        name=item["name"],
                        description=clean_desc,
                        inputSchema=item.get("inputSchema", {}),
                    )
                )
        return tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Invoke a tool on the MCP server via tools/call with auto-reconnection."""
        call_timeout = timeout or self.config.timeout_seconds

        for attempt in range(self.config.max_reconnect_attempts):
            try:
                if not self.is_running:
                    await self.start()

                res = await self._send_request(
                    "tools/call",
                    {"name": name, "arguments": arguments},
                    timeout=call_timeout,
                )
                return res

            except (MCPClientError, asyncio.TimeoutError) as ex:
                if attempt == self.config.max_reconnect_attempts - 1:
                    raise MCPClientError(f"Tool invocation '{name}' failed after retries: {ex}") from ex
                await self.close()
                await asyncio.sleep(0.5 * (attempt + 1))

        raise MCPClientError(f"Tool invocation '{name}' failed.")

    async def check_health(self) -> bool:
        """Check if server is responsive and initialized."""
        if not self.is_running:
            return False
        try:
            res = await self._send_request("ping", {}, timeout=5)
            return True
        except Exception:
            return self.is_running

    async def _send_request(
        self,
        method: str,
        params: dict[str, Any],
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Send a JSON-RPC 2.0 request and await response."""
        async with self._lock:
            self._request_id += 1
            req_id = self._request_id
            payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params,
            }

            if self.config.transport == MCPTransportType.STDIO:
                return await self._send_stdio_request(payload, timeout)
            else:
                return await self._send_http_request(payload, timeout)

    async def _send_stdio_request(self, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        if not self.process or not self.process.stdin or not self.process.stdout:
            raise MCPClientError(f"Server '{self.config.name}' is not running.")

        raw_bytes = (json.dumps(payload) + "\n").encode("utf-8")
        try:
            self.process.stdin.write(raw_bytes)
            await self.process.stdin.drain()
        except Exception as ex:
            raise MCPClientError(f"Failed to write to '{self.config.name}': {ex}") from ex

        try:
            line_bytes = await asyncio.wait_for(
                self.process.stdout.readline(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise MCPClientError(
                f"Request to MCP server '{self.config.name}' timed out after {timeout}s."
            )

        if not line_bytes:
            raise MCPClientError(f"MCP server '{self.config.name}' closed stdout stream unexpectedly.")

        try:
            data = json.loads(line_bytes.decode("utf-8", errors="replace").strip())
        except Exception as ex:
            raise MCPClientError(f"Malformed JSON-RPC response from '{self.config.name}': {ex}") from ex

        if "error" in data:
            err = data["error"]
            msg = err.get("message", "Unknown MCP error") if isinstance(err, dict) else str(err)
            raise MCPClientError(f"MCP error from '{self.config.name}': {msg}")

        return data.get("result", {})

    async def _send_http_request(self, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        if not self._http_client or not self._post_endpoint:
            raise MCPClientError(f"HTTP client for '{self.config.name}' is not connected.")

        try:
            resp = await self._http_client.post(
                self._post_endpoint,
                json=payload,
                timeout=float(timeout),
            )
            if resp.status_code >= 400:
                raise MCPClientError(f"HTTP error ({resp.status_code}) from '{self.config.name}': {resp.text}")

            data = resp.json()
            if "error" in data:
                err = data["error"]
                msg = err.get("message", "Unknown MCP error") if isinstance(err, dict) else str(err)
                raise MCPClientError(f"MCP error from '{self.config.name}': {msg}")

            return data.get("result", {})
        except Exception as ex:
            if isinstance(ex, MCPClientError):
                raise
            raise MCPClientError(f"HTTP request to '{self.config.name}' failed: {ex}") from ex

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC 2.0 notification."""
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        if self.config.transport == MCPTransportType.STDIO and self.process and self.process.stdin:
            try:
                self.process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
                await self.process.stdin.drain()
            except Exception:
                pass
        elif self._http_client and self._post_endpoint:
            try:
                await self._http_client.post(self._post_endpoint, json=payload, timeout=5.0)
            except Exception:
                pass

    async def close(self) -> None:
        """Cleanly close all connections and subprocesses."""
        self._is_initialized = False

        if self._http_client:
            try:
                await self._http_client.aclose()
            except Exception:
                pass
            self._http_client = None

        if self.process:
            proc = self.process
            self.process = None
            if proc.returncode is None:
                try:
                    if proc.stdin:
                        proc.stdin.close()
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        proc.kill()
                        await proc.wait()
                except Exception:
                    pass
