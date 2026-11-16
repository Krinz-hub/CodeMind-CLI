"""Official Google Drive REST API v3 connector (Phase 1)."""

from __future__ import annotations

import io
import json
from pathlib import Path
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


GDRIVE_BASE_URL = "https://www.googleapis.com/drive/v3/files"
GDRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"


class GoogleDriveConnector(GoogleBaseConnector):
    """Integrates official Google Drive API for file search, reading, creation, organization, and deletion."""

    manifest = ConnectorManifest(
        connector_id="google_drive",
        name="Google Drive",
        description="Search files, read documents, upload deliverables, organize folders, and manage Drive assets.",
        category="storage",
        version="1.0.0",
        icon="📁",
        auth_method=AuthMethod.OAUTH2,
        required_scopes=[
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/drive.file",
        ],
        actions=[
            ConnectorAction(
                name="search_files",
                description="Search files and folders in Google Drive by name, type, or query.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query or name pattern"},
                        "max_results": {"type": "integer", "description": "Maximum number of files to return", "default": 10},
                    },
                    "required": ["query"],
                },
            ),
            ConnectorAction(
                name="read_document",
                description="Read content of a Google Drive document or text file.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {"type": "string", "description": "Google Drive file ID to read"},
                    },
                    "required": ["file_id"],
                },
            ),
            ConnectorAction(
                name="create_file",
                description="Create a new text file or document directly in Google Drive.",
                risk_level=ActionRiskLevel.WRITE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the file to create"},
                        "content": {"type": "string", "description": "Content of the file"},
                        "mime_type": {"type": "string", "description": "MIME type (e.g. text/plain, text/markdown)", "default": "text/plain"},
                        "folder_id": {"type": "string", "description": "Optional destination folder ID"},
                    },
                    "required": ["name", "content"],
                },
            ),
            ConnectorAction(
                name="upload_file",
                description="Upload a local workspace file to Google Drive.",
                risk_level=ActionRiskLevel.WRITE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "local_path": {"type": "string", "description": "Workspace-relative path to local file"},
                        "name": {"type": "string", "description": "Optional destination file name"},
                        "folder_id": {"type": "string", "description": "Optional destination folder ID"},
                    },
                    "required": ["local_path"],
                },
            ),
            ConnectorAction(
                name="organize_folders",
                description="Create folders or move files between folders in Google Drive.",
                risk_level=ActionRiskLevel.WRITE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "'create_folder' or 'move_file'"},
                        "folder_name": {"type": "string", "description": "Folder name when action is 'create_folder'"},
                        "file_id": {"type": "string", "description": "File ID when action is 'move_file'"},
                        "parent_id": {"type": "string", "description": "Parent folder ID"},
                        "target_folder_id": {"type": "string", "description": "Destination folder ID when moving"},
                    },
                    "required": ["action"],
                },
            ),
            ConnectorAction(
                name="delete_file",
                description="Permanently delete a file or folder from Google Drive (SENSITIVE: requires human approval).",
                risk_level=ActionRiskLevel.SENSITIVE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {"type": "string", "description": "Google Drive file ID to delete"},
                    },
                    "required": ["file_id"],
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
            async with httpx.AsyncClient(timeout=30.0) as client:
                if action_name == "search_files":
                    return await self._search_files(client, headers, arguments)
                elif action_name == "read_document":
                    return await self._read_document(client, headers, arguments)
                elif action_name == "create_file":
                    return await self._create_file(client, headers, arguments)
                elif action_name == "upload_file":
                    return await self._upload_file(client, headers, arguments, context)
                elif action_name == "organize_folders":
                    return await self._organize_folders(client, headers, arguments)
                elif action_name == "delete_file":
                    return await self._delete_file(client, headers, arguments)
                else:
                    return ToolResult.error(f"Unknown Google Drive action '{action_name}'.")
        except httpx.HTTPStatusError as e:
            return ToolResult.error(f"Google Drive API error ({e.response.status_code}): {e.response.text[:200]}")
        except Exception as e:
            return ToolResult.error(f"Google Drive action failed: {str(e)}")

    async def _search_files(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        query_str = args.get("query", "")
        max_results = min(int(args.get("max_results", 10)), 50)
        q = f"name contains '{query_str}' and trashed = false"

        resp = await client.get(
            GDRIVE_BASE_URL,
            headers=headers,
            params={
                "q": q,
                "pageSize": max_results,
                "fields": "files(id, name, mimeType, size, modifiedTime, webViewLink)",
            },
        )
        if resp.status_code >= 400:
            return ToolResult.error(f"Drive search failed ({resp.status_code}): {resp.text}")

        files = resp.json().get("files", [])
        if not files:
            return ToolResult.success(f"No Google Drive files found matching query '{query_str}'.")

        lines = [f"Found {len(files)} file(s) matching '{query_str}':"]
        for f in files:
            fid = f.get("id")
            name = f.get("name")
            mtype = f.get("mimeType", "").split(".")[-1]
            mod = f.get("modifiedTime", "")
            lines.append(f"• [{fid}] {name} ({mtype}) - Modified: {mod}")

        return ToolResult.success("\n".join(lines))

    async def _read_document(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        file_id = args.get("file_id", "")
        # Inspect metadata to see if it's a Google Doc (requiring export)
        meta_resp = await client.get(f"{GDRIVE_BASE_URL}/{file_id}?fields=id,name,mimeType", headers=headers)
        if meta_resp.status_code >= 400:
            return ToolResult.error(f"Failed to fetch metadata for '{file_id}' ({meta_resp.status_code}): {meta_resp.text}")

        meta = meta_resp.json()
        mime_type = meta.get("mimeType", "")
        name = meta.get("name", "Document")

        if mime_type == "application/vnd.google-apps.document":
            # Export Google Doc as text/plain
            resp = await client.get(
                f"{GDRIVE_BASE_URL}/{file_id}/export?mimeType=text/plain",
                headers=headers,
            )
        else:
            # Download binary/text file
            resp = await client.get(
                f"{GDRIVE_BASE_URL}/{file_id}?alt=media",
                headers=headers,
            )

        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to read file content ({resp.status_code}): {resp.text}")

        content_text = resp.text
        return ToolResult.success(f"=== File: {name} (ID: {file_id}) ===\n\n{content_text}")

    async def _create_file(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        name = args.get("name", "untitled.txt")
        content = args.get("content", "")
        mime_type = args.get("mime_type", "text/plain")
        folder_id = args.get("folder_id")

        metadata: dict[str, Any] = {"name": name, "mimeType": mime_type}
        if folder_id:
            metadata["parents"] = [folder_id]

        files = {
            "data": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
            "file": (name, content.encode("utf-8"), mime_type),
        }

        resp = await client.post(GDRIVE_UPLOAD_URL, headers=headers, files=files)
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to create file '{name}' ({resp.status_code}): {resp.text}")

        created = resp.json()
        return ToolResult.success(f"Created Google Drive file '{name}' successfully. File ID: {created.get('id')}")

    async def _upload_file(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any], context: ExecutionContext) -> ToolResult:
        rel_path = args.get("local_path", "")
        target_path = context.sandbox.validate_path_access(rel_path, is_write=False)

        if not target_path.is_file():
            return ToolResult.error(f"Local file '{rel_path}' does not exist.")

        name = args.get("name") or target_path.name
        folder_id = args.get("folder_id")

        metadata: dict[str, Any] = {"name": name}
        if folder_id:
            metadata["parents"] = [folder_id]

        with open(target_path, "rb") as f:
            file_bytes = f.read()

        files = {
            "data": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
            "file": (name, file_bytes, "application/octet-stream"),
        }

        resp = await client.post(GDRIVE_UPLOAD_URL, headers=headers, files=files)
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to upload '{rel_path}' ({resp.status_code}): {resp.text}")

        res_data = resp.json()
        return ToolResult.success(f"Uploaded '{rel_path}' to Google Drive successfully as '{name}'. File ID: {res_data.get('id')}")

    async def _organize_folders(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        action = args.get("action", "").lower()

        if action == "create_folder":
            folder_name = args.get("folder_name", "New Folder")
            parent_id = args.get("parent_id")
            metadata: dict[str, Any] = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
            }
            if parent_id:
                metadata["parents"] = [parent_id]

            resp = await client.post(GDRIVE_BASE_URL, headers=headers, json=metadata)
            if resp.status_code >= 400:
                return ToolResult.error(f"Failed to create folder ({resp.status_code}): {resp.text}")

            fid = resp.json().get("id")
            return ToolResult.success(f"Created Google Drive folder '{folder_name}' successfully. Folder ID: {fid}")

        elif action == "move_file":
            file_id = args.get("file_id")
            target_folder_id = args.get("target_folder_id")
            if not file_id or not target_folder_id:
                return ToolResult.error("Must provide 'file_id' and 'target_folder_id' to move file.")

            # Retrieve current parents
            meta = await client.get(f"{GDRIVE_BASE_URL}/{file_id}?fields=parents", headers=headers)
            old_parents = ",".join(meta.json().get("parents", []))

            resp = await client.patch(
                f"{GDRIVE_BASE_URL}/{file_id}",
                headers=headers,
                params={"addParents": target_folder_id, "removeParents": old_parents},
            )
            if resp.status_code >= 400:
                return ToolResult.error(f"Failed to move file ({resp.status_code}): {resp.text}")

            return ToolResult.success(f"Moved file '{file_id}' to folder '{target_folder_id}' successfully.")

        return ToolResult.error(f"Unknown organize action '{action}'. Supported: 'create_folder', 'move_file'.")

    async def _delete_file(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        file_id = args.get("file_id", "")
        resp = await client.delete(f"{GDRIVE_BASE_URL}/{file_id}", headers=headers)
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to delete file '{file_id}' ({resp.status_code}): {resp.text}")

        return ToolResult.success(f"Permanently deleted Google Drive file '{file_id}'.")
