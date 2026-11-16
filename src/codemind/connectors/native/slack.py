"""Official Slack Web API connector (Phase 2)."""

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


SLACK_BASE_URL = "https://slack.com/api"


class SlackConnector(ConnectorAdapter):
    """Integrates official Slack Web API for channel listing, conversation history, and messaging."""

    manifest = ConnectorManifest(
        connector_id="slack",
        name="Slack",
        description="Inspect Slack channels, search workspace conversations, and post approved messages.",
        category="communication",
        version="1.0.0",
        icon="💼",
        auth_method=AuthMethod.BOT_TOKEN,
        actions=[
            ConnectorAction(
                name="list_channels",
                description="List accessible public and private Slack channels in the connected workspace.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "types": {"type": "string", "description": "Channel types: 'public_channel', 'private_channel', or both", "default": "public_channel,private_channel"},
                        "limit": {"type": "integer", "description": "Max channels to return", "default": 25},
                    },
                },
            ),
            ConnectorAction(
                name="read_channel",
                description="Read recent message history from a Slack channel.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "channel_id": {"type": "string", "description": "Slack channel ID (e.g. C01234567)"},
                        "limit": {"type": "integer", "description": "Number of messages to retrieve", "default": 20},
                    },
                    "required": ["channel_id"],
                },
            ),
            ConnectorAction(
                name="search_messages",
                description="Search for keyword matches in a Slack channel's recent conversation history.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "channel_id": {"type": "string", "description": "Slack channel ID to search"},
                        "query": {"type": "string", "description": "Search keyword"},
                        "limit": {"type": "integer", "description": "Scan depth", "default": 50},
                    },
                    "required": ["channel_id", "query"],
                },
            ),
            ConnectorAction(
                name="send_message",
                description="Post a message to a Slack channel or thread (SENSITIVE: requires human approval).",
                risk_level=ActionRiskLevel.SENSITIVE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "channel_id": {"type": "string", "description": "Destination Slack channel ID"},
                        "text": {"type": "string", "description": "Message text to post"},
                        "thread_ts": {"type": "string", "description": "Optional thread timestamp to reply in thread"},
                    },
                    "required": ["channel_id", "text"],
                },
            ),
        ],
    )

    async def get_auth_headers(self) -> dict[str, str]:
        token = await self.auth_manager.get_valid_access_token(self.connector_id)
        if not token:
            raise PermissionError("Slack bot token not configured. Run 'codemind connectors connect slack'.")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def check_health(self) -> ConnectorHealth:
        if not self.is_connected():
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.DISCONNECTED,
                message="Slack bot token not stored in vault.",
            )

        t0 = time.time()
        try:
            headers = await self.get_auth_headers()
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{SLACK_BASE_URL}/auth.test", headers=headers)
                latency_ms = (time.time() - t0) * 1000.0

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        team = data.get("team", "Slack Workspace")
                        user = data.get("user", "Bot")
                        return ConnectorHealth(
                            healthy=True,
                            status=ConnectionStatus.CONNECTED,
                            message=f"Connected to Slack team '{team}' as '{user}'.",
                            latency_ms=round(latency_ms, 2),
                            details={"team": team, "user": user, "team_id": data.get("team_id")},
                        )
                    else:
                        err = data.get("error", "auth_failed")
                        return ConnectorHealth(
                            healthy=False,
                            status=ConnectionStatus.ERROR,
                            message=f"Slack authentication failed: {err}",
                            latency_ms=round(latency_ms, 2),
                        )
                else:
                    return ConnectorHealth(
                        healthy=False,
                        status=ConnectionStatus.ERROR,
                        message=f"Slack HTTP error {resp.status_code}: {resp.text}",
                        latency_ms=round(latency_ms, 2),
                    )
        except Exception as ex:
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.ERROR,
                message=f"Slack connection check failed: {ex}",
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
                if action_name == "list_channels":
                    return await self._list_channels(client, headers, arguments)
                elif action_name == "read_channel":
                    return await self._read_channel(client, headers, arguments)
                elif action_name == "search_messages":
                    return await self._search_messages(client, headers, arguments)
                elif action_name == "send_message":
                    return await self._send_message(client, headers, arguments)
                else:
                    return ToolResult.error(f"Unknown Slack action '{action_name}'.")
        except httpx.HTTPStatusError as e:
            return ToolResult.error(f"Slack API error ({e.response.status_code}): {e.response.text[:200]}")
        except Exception as e:
            return ToolResult.error(f"Slack action failed: {str(e)}")

    async def _list_channels(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        types = args.get("types", "public_channel,private_channel")
        limit = min(int(args.get("limit", 25)), 100)

        resp = await client.get(
            f"{SLACK_BASE_URL}/conversations.list",
            headers=headers,
            params={"types": types, "limit": limit},
        )
        if resp.status_code >= 400:
            return ToolResult.error(f"Slack API error ({resp.status_code}): {resp.text}")

        data = resp.json()
        if not data.get("ok"):
            return ToolResult.error(f"Slack error: {data.get('error')}")

        channels = data.get("channels", [])
        if not channels:
            return ToolResult.success("No accessible channels found in this Slack workspace.")

        lines = [f"Found {len(channels)} Slack channel(s):"]
        for c in channels:
            cid = c.get("id")
            name = c.get("name")
            priv = "[private]" if c.get("is_private") else ""
            lines.append(f"• #{name} ({cid}) {priv}")

        return ToolResult.success("\n".join(lines))

    async def _read_channel(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        cid = args.get("channel_id", "")
        limit = min(int(args.get("limit", 20)), 100)

        resp = await client.get(
            f"{SLACK_BASE_URL}/conversations.history",
            headers=headers,
            params={"channel": cid, "limit": limit},
        )
        if resp.status_code >= 400:
            return ToolResult.error(f"Slack API error ({resp.status_code}): {resp.text}")

        data = resp.json()
        if not data.get("ok"):
            return ToolResult.error(f"Slack error: {data.get('error')}")

        messages = data.get("messages", [])
        if not messages:
            return ToolResult.success(f"Channel {cid} history is empty.")

        lines = [f"=== Slack Channel {cid} (Last {len(messages)} messages) ==="]
        for m in reversed(messages):
            user = m.get("user", "Unknown")
            ts = m.get("ts", "")
            text = m.get("text", "")
            lines.append(f"[{ts}] {user}: {text}")

        return ToolResult.success("\n".join(lines))

    async def _search_messages(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        cid = args.get("channel_id", "")
        query = args.get("query", "").lower()
        limit = min(int(args.get("limit", 50)), 100)

        resp = await client.get(
            f"{SLACK_BASE_URL}/conversations.history",
            headers=headers,
            params={"channel": cid, "limit": limit},
        )
        if resp.status_code >= 400:
            return ToolResult.error(f"Slack API error ({resp.status_code}): {resp.text}")

        data = resp.json()
        if not data.get("ok"):
            return ToolResult.error(f"Slack error: {data.get('error')}")

        messages = data.get("messages", [])
        matched = [m for m in messages if query in m.get("text", "").lower()]
        if not matched:
            return ToolResult.success(f"No messages found containing '{query}' in channel {cid}.")

        lines = [f"Found {len(matched)} message(s) containing '{query}':"]
        for m in matched:
            user = m.get("user", "Unknown")
            ts = m.get("ts", "")
            text = m.get("text", "")
            lines.append(f"• [{ts}] {user}: {text}")

        return ToolResult.success("\n".join(lines))

    async def _send_message(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        cid = args.get("channel_id", "")
        text = args.get("text", "")
        thread_ts = args.get("thread_ts")

        payload: dict[str, Any] = {"channel": cid, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts

        resp = await client.post(f"{SLACK_BASE_URL}/chat.postMessage", headers=headers, json=payload)
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to send Slack message ({resp.status_code}): {resp.text}")

        data = resp.json()
        if not data.get("ok"):
            return ToolResult.error(f"Slack error: {data.get('error')}")

        ts = data.get("ts", "")
        return ToolResult.success(f"Message sent to Slack channel '{cid}' successfully. Timestamp: {ts}")
