"""Official Notion API connector (Phase 2)."""

from __future__ import annotations

import json
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


NOTION_BASE_URL = "https://api.notion.com/v1"
NOTION_API_VERSION = "2022-06-28"


class NotionConnector(ConnectorAdapter):
    """Integrates official Notion API for page/database search, reading, creation, and updates."""

    manifest = ConnectorManifest(
        connector_id="notion",
        name="Notion",
        description="Search workspace pages and databases, inspect page blocks, create notes, and update records.",
        category="productivity",
        version="1.0.0",
        icon="📓",
        auth_method=AuthMethod.API_KEY,
        actions=[
            ConnectorAction(
                name="search_pages",
                description="Search for pages and databases matching a query in the connected Notion workspace.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keyword or title query", "default": ""},
                        "filter_type": {"type": "string", "description": "Filter by object type: 'page' or 'database'", "default": "page"},
                        "limit": {"type": "integer", "description": "Maximum number of results (max 100)", "default": 20},
                    },
                },
            ),
            ConnectorAction(
                name="read_page",
                description="Retrieve Notion page metadata and child block contents.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "page_id": {"type": "string", "description": "UUID of the Notion page to read"},
                    },
                    "required": ["page_id"],
                },
            ),
            ConnectorAction(
                name="create_page",
                description="Create a new Notion page inside a parent page or database (WRITE).",
                risk_level=ActionRiskLevel.WRITE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Page title"},
                        "parent_page_id": {"type": "string", "description": "Parent page UUID (either parent_page_id or parent_database_id required)"},
                        "parent_database_id": {"type": "string", "description": "Parent database UUID"},
                        "content": {"type": "string", "description": "Initial text content paragraph"},
                    },
                    "required": ["title"],
                },
            ),
            ConnectorAction(
                name="update_page",
                description="Update page properties or archive/delete a page in Notion (WRITE).",
                risk_level=ActionRiskLevel.WRITE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "page_id": {"type": "string", "description": "UUID of the page to update"},
                        "title": {"type": "string", "description": "New title for the page"},
                        "archived": {"type": "boolean", "description": "Set to true to archive the page"},
                    },
                    "required": ["page_id"],
                },
            ),
            ConnectorAction(
                name="query_database",
                description="Query rows and structured properties from an authorized Notion database.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "database_id": {"type": "string", "description": "UUID of the Notion database to query"},
                        "filter_json": {"type": "string", "description": "Optional Notion filter JSON string"},
                        "limit": {"type": "integer", "description": "Maximum records to retrieve", "default": 50},
                    },
                    "required": ["database_id"],
                },
            ),
        ],
    )

    async def get_auth_headers(self) -> dict[str, str]:
        token = await self.auth_manager.get_valid_access_token(self.connector_id)
        if not token:
            raise PermissionError("Notion API token not configured. Run 'codemind connectors connect notion'.")
        return {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json",
        }

    async def check_health(self) -> ConnectorHealth:
        if not self.is_connected():
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.DISCONNECTED,
                message="Notion API token is not configured.",
            )

        t0 = time.time()
        try:
            headers = await self.get_auth_headers()
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{NOTION_BASE_URL}/users/me", headers=headers)
                latency = (time.time() - t0) * 1000

                if res.status_code == 200:
                    data = res.json()
                    user_name = data.get("name", "Notion Bot")
                    return ConnectorHealth(
                        healthy=True,
                        status=ConnectionStatus.CONNECTED,
                        message=f"Connected to Notion as '{user_name}'",
                        latency_ms=round(latency, 2),
                    )
                elif res.status_code in (401, 403):
                    return ConnectorHealth(
                        healthy=False,
                        status=ConnectionStatus.EXPIRED,
                        message="Invalid or revoked Notion integration token.",
                    )
                else:
                    return ConnectorHealth(
                        healthy=False,
                        status=ConnectionStatus.ERROR,
                        message=f"Notion API returned HTTP {res.status_code}: {res.text[:120]}",
                    )
        except Exception as e:
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.ERROR,
                message=f"Connection failure: {str(e)}",
            )

    async def execute_action(
        self,
        action_name: str,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        dispatch = {
            "search_pages": self._action_search_pages,
            "read_page": self._action_read_page,
            "create_page": self._action_create_page,
            "update_page": self._action_update_page,
            "query_database": self._action_query_database,
        }

        handler = dispatch.get(action_name)
        if not handler:
            return ToolResult.error(f"Unknown action '{action_name}' for Notion connector.")

        try:
            return await handler(params, context)
        except httpx.HTTPStatusError as e:
            err_msg = f"Notion API error (HTTP {e.response.status_code}): {e.response.text[:200]}"
            return ToolResult.error(err_msg, metadata={"status_code": e.response.status_code})
        except Exception as e:
            return ToolResult.error(f"Notion action failed: {str(e)}")

    async def _action_search_pages(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        query = params.get("query", "")
        filter_type = params.get("filter_type", "page")
        limit = min(int(params.get("limit", 20)), 100)

        headers = await self.get_auth_headers()
        body: dict[str, Any] = {"page_size": limit}
        if query:
            body["query"] = query
        if filter_type in ("page", "database"):
            body["filter"] = {"value": filter_type, "property": "object"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(f"{NOTION_BASE_URL}/search", headers=headers, json=body)
            res.raise_for_status()
            data = res.json()

        results = []
        for item in data.get("results", []):
            title = ""
            if item.get("object") == "page":
                props = item.get("properties", {})
                for p_val in props.values():
                    if p_val.get("type") == "title":
                        title = "".join(t.get("plain_text", "") for t in p_val.get("title", []))
                        break
            elif item.get("object") == "database":
                title = "".join(t.get("plain_text", "") for t in item.get("title", []))

            results.append({
                "id": item.get("id"),
                "object": item.get("object"),
                "title": title or "Untitled",
                "url": item.get("url"),
                "last_edited_time": item.get("last_edited_time"),
            })

        return ToolResult.success(
            f"Found {len(results)} Notion item(s) matching '{query}'.\n"
            + json.dumps(results, indent=2),
            metadata={"results": results, "total": len(results)},
        )

    async def _action_read_page(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        page_id = params.get("page_id", "").strip().replace("-", "")
        if not page_id:
            return ToolResult.error("Parameter 'page_id' is required.")

        headers = await self.get_auth_headers()
        async with httpx.AsyncClient(timeout=15.0) as client:
            page_res = await client.get(f"{NOTION_BASE_URL}/pages/{page_id}", headers=headers)
            page_res.raise_for_status()
            page_data = page_res.json()

            blocks_res = await client.get(f"{NOTION_BASE_URL}/blocks/{page_id}/children?page_size=50", headers=headers)
            blocks_res.raise_for_status()
            blocks_data = blocks_res.json()

        text_blocks = []
        for b in blocks_data.get("results", []):
            b_type = b.get("type", "")
            content = b.get(b_type, {})
            rich_texts = content.get("rich_text", [])
            txt = "".join(t.get("plain_text", "") for t in rich_texts)
            if txt:
                text_blocks.append(f"[{b_type}] {txt}")

        content_str = "\n".join(text_blocks) if text_blocks else "(No text blocks found)"
        return ToolResult.success(
            f"Notion Page ID: {page_id}\nURL: {page_data.get('url', '')}\n\nContent:\n{content_str}",
            metadata={"page": page_data, "blocks": blocks_data.get("results", [])},
        )

    async def _action_create_page(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        title = params.get("title", "").strip()
        parent_page_id = params.get("parent_page_id")
        parent_database_id = params.get("parent_database_id")
        content = params.get("content", "").strip()

        if not parent_page_id and not parent_database_id:
            return ToolResult.error("Either 'parent_page_id' or 'parent_database_id' must be specified.")

        headers = await self.get_auth_headers()

        payload: dict[str, Any] = {}
        if parent_page_id:
            payload["parent"] = {"page_id": parent_page_id.replace("-", "")}
            payload["properties"] = {
                "title": {
                    "title": [{"text": {"content": title}}],
                }
            }
        else:
            payload["parent"] = {"database_id": parent_database_id.replace("-", "")}
            payload["properties"] = {
                "Name": {
                    "title": [{"text": {"content": title}}],
                }
            }

        if content:
            payload["children"] = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": content}}],
                    },
                }
            ]

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(f"{NOTION_BASE_URL}/pages", headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()

        page_id = data.get("id")
        url = data.get("url")
        return ToolResult.success(
            f"Notion page created successfully!\nID: {page_id}\nURL: {url}",
            metadata={"id": page_id, "url": url},
        )

    async def _action_update_page(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        page_id = params.get("page_id", "").strip().replace("-", "")
        title = params.get("title")
        archived = params.get("archived")

        if not page_id:
            return ToolResult.error("Parameter 'page_id' is required.")

        headers = await self.get_auth_headers()
        payload: dict[str, Any] = {}

        if title is not None:
            payload["properties"] = {
                "title": {
                    "title": [{"text": {"content": title}}],
                }
            }
        if archived is not None:
            payload["archived"] = archived

        if not payload:
            return ToolResult.error("No update fields provided (provide 'title' or 'archived').")

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.patch(f"{NOTION_BASE_URL}/pages/{page_id}", headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()

        return ToolResult.success(
            f"Notion page '{page_id}' updated successfully.",
            metadata={"id": page_id, "archived": data.get("archived")},
        )

    async def _action_query_database(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        database_id = params.get("database_id", "").strip().replace("-", "")
        filter_json = params.get("filter_json")
        limit = min(int(params.get("limit", 50)), 100)

        if not database_id:
            return ToolResult.error("Parameter 'database_id' is required.")

        headers = await self.get_auth_headers()
        body: dict[str, Any] = {"page_size": limit}
        if filter_json:
            try:
                body["filter"] = json.loads(filter_json)
            except json.JSONDecodeError as e:
                return ToolResult.error(f"Invalid filter_json format: {str(e)}")

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(f"{NOTION_BASE_URL}/databases/{database_id}/query", headers=headers, json=body)
            res.raise_for_status()
            data = res.json()

        results = []
        for row in data.get("results", []):
            results.append({
                "id": row.get("id"),
                "created_time": row.get("created_time"),
                "url": row.get("url"),
                "properties_keys": list(row.get("properties", {}).keys()),
            })

        return ToolResult.success(
            f"Retrieved {len(results)} rows from Notion database '{database_id}'.\n"
            + json.dumps(results, indent=2),
            metadata={"results": results, "total": len(results)},
        )
