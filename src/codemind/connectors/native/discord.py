"""Official Discord REST API v10 connector (Phase 2)."""

from __future__ import annotations

import time
from typing import Any
import httpx

from codemind.connectors.base import ConnectorAdapter
from codemind.connectors.models import (
    ActionRiskLevel,
    AuthMethod,
    ConnectionStatus,
    ConnectorAction,
    ConnectorHealth,
    ConnectorManifest,
)
from codemind.tools.base import ExecutionContext, ToolResult


DISCORD_BASE_URL = "https://discord.com/api/v10"


class DiscordConnector(ConnectorAdapter):
    """Integrates official Discord REST API v10 for channel reading, searching, and sending messages."""

    manifest = ConnectorManifest(
        connector_id="discord",
        name="Discord",
        description="Read authorized Discord channels, search message history, and post approved messages.",
        category="communication",
        version="1.0.0",
        icon="💬",
        auth_method=AuthMethod.BOT_TOKEN,
        actions=[
            ConnectorAction(
                name="read_channel",
                description="Read recent messages from an authorized Discord text channel.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "channel_id": {"type": "string", "description": "Discord channel snowflake ID"},
                        "limit": {"type": "integer", "description": "Maximum number of messages (1-100)", "default": 20},
                    },
                    "required": ["channel_id"],
                },
            ),
            ConnectorAction(
                name="search_messages",
                description="Search for keyword occurrences in a Discord channel's recent history.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "channel_id": {"type": "string", "description": "Discord channel ID"},
                        "query": {"type": "string", "description": "Keyword to search for"},
                        "limit": {"type": "integer", "description": "Number of messages to search", "default": 50},
                    },
                    "required": ["channel_id", "query"],
                },
            ),
            ConnectorAction(
                name="send_message",
                description="Send a message to a Discord channel (SENSITIVE: requires human approval).",
                risk_level=ActionRiskLevel.SENSITIVE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "channel_id": {"type": "string", "description": "Discord channel ID"},
                        "content": {"type": "string", "description": "Text content of the message (max 2000 chars)"},
                    },
                    "required": ["channel_id", "content"],
                },
            ),
        ],
    )

    async def get_auth_headers(self) -> dict[str, str]:
        token = await self.auth_manager.get_valid_access_token(self.connector_id)
        if not token:
            raise PermissionError("Discord bot token not configured. Run 'codemind connectors connect discord'.")
        # Ensure Bot prefix if not already present
        auth_str = token if token.startswith("Bot ") else f"Bot {token}"
        return {
            "Authorization": auth_str,
            "Content-Type": "application/json",
            "User-Agent": "CodeMind-CLI (https://github.com/codemind, 1.0.0)",
        }

    async def check_health(self) -> ConnectorHealth:
        if not self.is_connected():
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.DISCONNECTED,
                message="Discord bot token not stored in vault.",
            )

        t0 = time.time()
        try:
            headers = await self.get_auth_headers()
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{DISCORD_BASE_URL}/users/@me", headers=headers)
                latency_ms = (time.time() - t0) * 1000.0

                if resp.status_code == 200:
                    data = resp.json()
                    bot_name = data.get("username", "Discord Bot")
                    return ConnectorHealth(
                        healthy=True,
                        status=ConnectionStatus.CONNECTED,
                        message=f"Connected as Discord Bot '{bot_name}' (ID: {data.get('id')}).",
                        latency_ms=round(latency_ms, 2),
                        details={"bot_name": bot_name, "id": data.get("id")},
                    )
                elif resp.status_code == 401:
                    return ConnectorHealth(
                        healthy=False,
                        status=ConnectionStatus.EXPIRED,
                        message="Discord authorization failed (401 Unauthorized). Invalid bot token.",
                        latency_ms=round(latency_ms, 2),
                    )
                else:
                    return ConnectorHealth(
                        healthy=False,
                        status=ConnectionStatus.ERROR,
                        message=f"Discord API returned status {resp.status_code}: {resp.text}",
                        latency_ms=round(latency_ms, 2),
                    )
        except Exception as ex:
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.ERROR,
                message=f"Discord connection error: {ex}",
            )

    async def execute_action(
        self,
        action_name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        headers = await self.get_auth_headers()

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                if action_name == "read_channel":
                    return await self._read_channel(client, headers, arguments)
                elif action_name == "search_messages":
                    return await self._search_messages(client, headers, arguments)
                elif action_name == "send_message":
                    return await self._send_message(client, headers, arguments)
                else:
                    return ToolResult.error(f"Unknown Discord action '{action_name}'.")
        except httpx.HTTPStatusError as e:
            return ToolResult.error(f"Discord API error ({e.response.status_code}): {e.response.text[:200]}")
        except Exception as e:
            return ToolResult.error(f"Discord action failed: {str(e)}")

    async def _read_channel(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        cid = args.get("channel_id", "")
        limit = min(int(args.get("limit", 20)), 100)

        resp = await client.get(
            f"{DISCORD_BASE_URL}/channels/{cid}/messages",
            headers=headers,
            params={"limit": limit},
        )
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to read Discord channel ({resp.status_code}): {resp.text}")

        messages = resp.json()
        if not messages:
            return ToolResult.success("Channel history is empty.")

        # Discord returns newest first, reverse for chronological read
        lines = [f"=== Discord Channel {cid} (Last {len(messages)} messages) ==="]
        for m in reversed(messages):
            author = m.get("author", {}).get("username", "Unknown")
            ts = m.get("timestamp", "")
            content = m.get("content", "")
            lines.append(f"[{ts}] {author}: {content}")

        return ToolResult.success("\n".join(lines))

    async def _search_messages(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        cid = args.get("channel_id", "")
        query = args.get("query", "").lower()
        limit = min(int(args.get("limit", 50)), 100)

        resp = await client.get(
            f"{DISCORD_BASE_URL}/channels/{cid}/messages",
            headers=headers,
            params={"limit": limit},
        )
        if resp.status_code >= 400:
            return ToolResult.error(f"Discord search failed ({resp.status_code}): {resp.text}")

        messages = resp.json()
        matched = [m for m in messages if query in m.get("content", "").lower()]
        if not matched:
            return ToolResult.success(f"No messages found matching '{query}' in channel {cid}.")

        lines = [f"Found {len(matched)} message(s) containing '{query}':"]
        for m in matched:
            author = m.get("author", {}).get("username", "Unknown")
            ts = m.get("timestamp", "")
            content = m.get("content", "")
            lines.append(f"• [{ts}] {author}: {content}")

        return ToolResult.success("\n".join(lines))

    async def _send_message(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        cid = args.get("channel_id", "")
        content = args.get("content", "")
        if not content.strip():
            return ToolResult.error("Cannot send empty message.")

        resp = await client.post(
            f"{DISCORD_BASE_URL}/channels/{cid}/messages",
            headers=headers,
            json={"content": content},
        )
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to send Discord message ({resp.status_code}): {resp.text}")

        msg = resp.json()
        mid = msg.get("id", "unknown")
        return ToolResult.success(f"Message sent successfully to Discord channel {cid}. Message ID: {mid}")
