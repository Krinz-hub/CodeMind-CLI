"""Official Google Gmail REST API connector (Phase 1)."""

from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any
import httpx

from codemind.connectors.models import (
    ActionRiskLevel,
    AuthMethod,
    ConnectorAction,
    ConnectorManifest,
)
from codemind.connectors.native.google_base import GoogleBaseConnector
from codemind.tools.base import ExecutionContext, ToolResult


GMAIL_BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailConnector(GoogleBaseConnector):
    """Integrates official Gmail API for searching, reading, drafting, and sending emails."""

    manifest = ConnectorManifest(
        connector_id="gmail",
        name="Gmail",
        description="Search inbox, read threads, draft messages, and send authorized emails.",
        category="communication",
        version="1.0.0",
        icon="📧",
        auth_method=AuthMethod.OAUTH2,
        required_scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.send",
        ],
        actions=[
            ConnectorAction(
                name="search_emails",
                description="Search inbox emails using Gmail query syntax (e.g. 'is:unread', 'from:colleague', 'subject:report').",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Gmail search query string"},
                        "max_results": {"type": "integer", "description": "Maximum number of messages to return", "default": 5},
                    },
                    "required": ["query"],
                },
            ),
            ConnectorAction(
                name="read_thread",
                description="Read full conversation thread including all messages, authors, dates, and bodies.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "thread_id": {"type": "string", "description": "Gmail thread ID to retrieve"},
                    },
                    "required": ["thread_id"],
                },
            ),
            ConnectorAction(
                name="summarize_conversations",
                description="Fetch and aggregate conversations matching a search query for fast summarization.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query filter for conversations"},
                        "max_threads": {"type": "integer", "description": "Maximum number of threads to inspect", "default": 3},
                    },
                    "required": ["query"],
                },
            ),
            ConnectorAction(
                name="create_draft",
                description="Create an email draft in Gmail without sending it.",
                risk_level=ActionRiskLevel.WRITE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address"},
                        "subject": {"type": "string", "description": "Email subject line"},
                        "body": {"type": "string", "description": "Email plain text body"},
                        "cc": {"type": "string", "description": "Optional CC recipient(s)"},
                    },
                    "required": ["to", "subject", "body"],
                },
            ),
            ConnectorAction(
                name="send_email",
                description="Send an email to a recipient (SENSITIVE: requires explicit human authorization).",
                risk_level=ActionRiskLevel.SENSITIVE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address"},
                        "subject": {"type": "string", "description": "Email subject line"},
                        "body": {"type": "string", "description": "Email plain text body"},
                        "cc": {"type": "string", "description": "Optional CC recipient(s)"},
                    },
                    "required": ["to", "subject", "body"],
                },
            ),
        ],
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
                if action_name == "search_emails":
                    return await self._search_emails(client, headers, arguments)
                elif action_name == "read_thread":
                    return await self._read_thread(client, headers, arguments)
                elif action_name == "summarize_conversations":
                    return await self._summarize_conversations(client, headers, arguments)
                elif action_name == "create_draft":
                    return await self._create_draft(client, headers, arguments)
                elif action_name == "send_email":
                    return await self._send_email(client, headers, arguments)
                else:
                    return ToolResult.error(f"Unknown Gmail action '{action_name}'.")
        except httpx.HTTPStatusError as e:
            return ToolResult.error(f"Gmail API error ({e.response.status_code}): {e.response.text[:200]}")
        except Exception as e:
            return ToolResult.error(f"Gmail action failed: {str(e)}")

    async def _search_emails(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "")
        max_results = min(int(args.get("max_results", 5)), 20)

        resp = await client.get(
            f"{GMAIL_BASE_URL}/messages",
            headers=headers,
            params={"q": query, "maxResults": max_results},
        )
        if resp.status_code >= 400:
            return ToolResult.error(f"Gmail search failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        messages = data.get("messages", [])
        if not messages:
            return ToolResult.success(f"No emails found matching query '{query}'.")

        # Fetch basic header metadata for each matching message
        results_summary: list[str] = [f"Found {len(messages)} email(s) for query '{query}':"]
        for msg in messages:
            mid = msg["id"]
            m_resp = await client.get(
                f"{GMAIL_BASE_URL}/messages/{mid}",
                headers=headers,
                params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            )
            if m_resp.status_code == 200:
                m_data = m_resp.json()
                headers_list = m_data.get("payload", {}).get("headers", [])
                hdr_map = {h.get("name", ""): h.get("value", "") for h in headers_list}
                results_summary.append(
                    f"• [ID: {mid}] Subject: '{hdr_map.get('Subject', '(No Subject)')}' | From: {hdr_map.get('From', '')} | Date: {hdr_map.get('Date', '')} | Snippet: {m_data.get('snippet', '')}"
                )

        return ToolResult.success("\n".join(results_summary))

    async def _read_thread(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        thread_id = args.get("thread_id", "")
        resp = await client.get(f"{GMAIL_BASE_URL}/threads/{thread_id}", headers=headers)
        if resp.status_code >= 400:
            return ToolResult.error(f"Gmail thread retrieval failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        messages = data.get("messages", [])
        if not messages:
            return ToolResult.success(f"Thread '{thread_id}' is empty.")

        thread_lines: list[str] = [f"=== Gmail Thread: {thread_id} ({len(messages)} message(s)) ==="]
        for idx, msg in enumerate(messages, 1):
            hdr_list = msg.get("payload", {}).get("headers", [])
            hdr_map = {h.get("name", ""): h.get("value", "") for h in hdr_list}
            snippet = msg.get("snippet", "")
            thread_lines.append(
                f"\n--- Message {idx} [ID: {msg.get('id')}] ---\n"
                f"From: {hdr_map.get('From', 'Unknown')}\n"
                f"To: {hdr_map.get('To', 'Unknown')}\n"
                f"Date: {hdr_map.get('Date', 'Unknown')}\n"
                f"Subject: {hdr_map.get('Subject', '(No Subject)')}\n\n"
                f"{snippet}"
            )
        return ToolResult.success("\n".join(thread_lines))

    async def _summarize_conversations(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "")
        max_threads = min(int(args.get("max_threads", 3)), 10)

        resp = await client.get(
            f"{GMAIL_BASE_URL}/threads",
            headers=headers,
            params={"q": query, "maxResults": max_threads},
        )
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to fetch conversations ({resp.status_code}): {resp.text}")

        threads = resp.json().get("threads", [])
        if not threads:
            return ToolResult.success(f"No conversations found matching query '{query}'.")

        summary_chunks: list[str] = [f"Aggregated {len(threads)} conversation(s) for query '{query}':\n"]
        for t in threads:
            tid = t["id"]
            t_res = await self._read_thread(client, headers, {"thread_id": tid})
            summary_chunks.append(t_res.content)

        return ToolResult.success("\n\n".join(summary_chunks))

    def _create_raw_message(self, to: str, subject: str, body: str, cc: str | None = None) -> str:
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        msg.set_content(body)
        raw_bytes = msg.as_bytes()
        return base64.urlsafe_b64encode(raw_bytes).decode("ascii")

    async def _create_draft(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        raw_b64 = self._create_raw_message(
            to=args.get("to", ""),
            subject=args.get("subject", ""),
            body=args.get("body", ""),
            cc=args.get("cc"),
        )
        payload = {"message": {"raw": raw_b64}}
        resp = await client.post(f"{GMAIL_BASE_URL}/drafts", headers=headers, json=payload)
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to create draft ({resp.status_code}): {resp.text}")

        data = resp.json()
        draft_id = data.get("id", "unknown")
        return ToolResult.success(f"Draft created successfully. Draft ID: {draft_id}")

    async def _send_email(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        raw_b64 = self._create_raw_message(
            to=args.get("to", ""),
            subject=args.get("subject", ""),
            body=args.get("body", ""),
            cc=args.get("cc"),
        )
        payload = {"raw": raw_b64}
        resp = await client.post(f"{GMAIL_BASE_URL}/messages/send", headers=headers, json=payload)
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to send email ({resp.status_code}): {resp.text}")

        data = resp.json()
        msg_id = data.get("id", "unknown")
        thread_id = data.get("threadId", "unknown")
        return ToolResult.success(f"Email sent successfully to '{args.get('to')}'. Message ID: {msg_id}, Thread ID: {thread_id}")
