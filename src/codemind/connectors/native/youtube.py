"""Official YouTube Data API v3 connector (Phase 1)."""

from __future__ import annotations

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


YOUTUBE_BASE_URL = "https://www.googleapis.com/youtube/v3"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=multipart&part=snippet,status"


class YouTubeConnector(GoogleBaseConnector):
    """Integrates official YouTube Data API v3 for video search, metadata retrieval, playlists, and video uploads."""

    manifest = ConnectorManifest(
        connector_id="youtube",
        name="YouTube",
        description="Search videos, inspect channel metadata, manage playlists, view analytics, and upload videos.",
        category="media",
        version="1.0.0",
        icon="▶️",
        auth_method=AuthMethod.OAUTH2,
        required_scopes=[
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube.upload",
        ],
        actions=[
            ConnectorAction(
                name="search_videos",
                description="Search YouTube public videos by query or keywords.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keyword or phrase"},
                        "max_results": {"type": "integer", "description": "Max results to return", "default": 5},
                    },
                    "required": ["query"],
                },
            ),
            ConnectorAction(
                name="get_channel_info",
                description="Retrieve YouTube channel statistics, title, and subscriber metrics.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "channel_id": {"type": "string", "description": "Optional YouTube channel ID (defaults to authenticated user channel)"},
                    },
                },
            ),
            ConnectorAction(
                name="get_video_metadata",
                description="Retrieve detailed video metadata, views, likes, tags, and description.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "video_id": {"type": "string", "description": "11-character YouTube video ID"},
                    },
                    "required": ["video_id"],
                },
            ),
            ConnectorAction(
                name="get_analytics",
                description="Retrieve high-level views, watch time, and subscriber counts for authenticated channel.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "description": "Number of days of analytics to summarize", "default": 30},
                    },
                },
            ),
            ConnectorAction(
                name="manage_playlists",
                description="List, create, or add videos to authorized YouTube playlists.",
                risk_level=ActionRiskLevel.WRITE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "'list', 'create', or 'add_video'"},
                        "title": {"type": "string", "description": "Playlist title when creating"},
                        "description": {"type": "string", "description": "Playlist description"},
                        "playlist_id": {"type": "string", "description": "Target playlist ID when adding video"},
                        "video_id": {"type": "string", "description": "Video ID when adding to playlist"},
                    },
                    "required": ["action"],
                },
            ),
            ConnectorAction(
                name="upload_video",
                description="Upload a video to YouTube with title, description, and privacy (SENSITIVE: requires human approval).",
                risk_level=ActionRiskLevel.SENSITIVE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "local_path": {"type": "string", "description": "Workspace-relative path to video file (.mp4, .mov, etc.)"},
                        "title": {"type": "string", "description": "Video title"},
                        "description": {"type": "string", "description": "Video description"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional keyword tags"},
                        "privacy_status": {"type": "string", "description": "'private', 'unlisted', or 'public'", "default": "private"},
                    },
                    "required": ["local_path", "title"],
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
            async with httpx.AsyncClient(timeout=45.0) as client:
                if action_name == "search_videos":
                    return await self._search_videos(client, headers, arguments)
                elif action_name == "get_channel_info":
                    return await self._get_channel_info(client, headers, arguments)
                elif action_name == "get_video_metadata":
                    return await self._get_video_metadata(client, headers, arguments)
                elif action_name == "get_analytics":
                    return await self._get_analytics(client, headers, arguments)
                elif action_name == "manage_playlists":
                    return await self._manage_playlists(client, headers, arguments)
                elif action_name == "upload_video":
                    return await self._upload_video(client, headers, arguments, context)
                else:
                    return ToolResult.error(f"Unknown YouTube action '{action_name}'.")
        except httpx.HTTPStatusError as e:
            return ToolResult.error(f"YouTube API error ({e.response.status_code}): {e.response.text[:200]}")
        except Exception as e:
            return ToolResult.error(f"YouTube action failed: {str(e)}")

    async def _search_videos(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        query = args.get("query", "")
        max_results = min(int(args.get("max_results", 5)), 25)

        resp = await client.get(
            f"{YOUTUBE_BASE_URL}/search",
            headers=headers,
            params={"part": "snippet", "q": query, "type": "video", "maxResults": max_results},
        )
        if resp.status_code >= 400:
            return ToolResult.error(f"YouTube search failed ({resp.status_code}): {resp.text}")

        items = resp.json().get("items", [])
        if not items:
            return ToolResult.success(f"No YouTube videos found matching query '{query}'.")

        lines = [f"Found {len(items)} YouTube video(s) for query '{query}':"]
        for it in items:
            vid = it.get("id", {}).get("videoId")
            snip = it.get("snippet", {})
            title = snip.get("title", "")
            channel = snip.get("channelTitle", "")
            lines.append(f"• [{vid}] {title} (Channel: {channel}) -> https://youtube.com/watch?v={vid}")

        return ToolResult.success("\n".join(lines))

    async def _get_channel_info(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        params: dict[str, Any] = {"part": "snippet,statistics"}
        if "channel_id" in args and args["channel_id"]:
            params["id"] = args["channel_id"]
        else:
            params["mine"] = "true"

        resp = await client.get(f"{YOUTUBE_BASE_URL}/channels", headers=headers, params=params)
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to fetch channel info ({resp.status_code}): {resp.text}")

        items = resp.json().get("items", [])
        if not items:
            return ToolResult.error("No channel found for authenticated user or given ID.")

        ch = items[0]
        snip = ch.get("snippet", {})
        stats = ch.get("statistics", {})

        info = (
            f"=== YouTube Channel: {snip.get('title')} ===\n"
            f"Channel ID   : {ch.get('id')}\n"
            f"Custom URL   : {snip.get('customUrl', 'N/A')}\n"
            f"Subscribers  : {stats.get('subscriberCount', '0')}\n"
            f"Total Views  : {stats.get('viewCount', '0')}\n"
            f"Total Videos : {stats.get('videoCount', '0')}\n"
            f"Description  : {snip.get('description', '')}"
        )
        return ToolResult.success(info)

    async def _get_video_metadata(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        video_id = args.get("video_id", "")
        resp = await client.get(
            f"{YOUTUBE_BASE_URL}/videos",
            headers=headers,
            params={"part": "snippet,statistics,contentDetails", "id": video_id},
        )
        if resp.status_code >= 400:
            return ToolResult.error(f"Failed to fetch video metadata ({resp.status_code}): {resp.text}")

        items = resp.json().get("items", [])
        if not items:
            return ToolResult.error(f"Video '{video_id}' not found.")

        v = items[0]
        snip = v.get("snippet", {})
        stats = v.get("statistics", {})
        dur = v.get("contentDetails", {}).get("duration", "N/A")

        info = (
            f"=== Video Metadata: {snip.get('title')} ===\n"
            f"Video ID     : {video_id}\n"
            f"Channel      : {snip.get('channelTitle')}\n"
            f"Published At : {snip.get('publishedAt')}\n"
            f"Duration     : {dur}\n"
            f"Views        : {stats.get('viewCount', '0')}\n"
            f"Likes        : {stats.get('likeCount', '0')}\n"
            f"Comments     : {stats.get('commentCount', '0')}\n"
            f"Tags         : {', '.join(snip.get('tags', []))}\n\n"
            f"Description:\n{snip.get('description', '')}"
        )
        return ToolResult.success(info)

    async def _get_analytics(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        # High level summary via channel statistics
        return await self._get_channel_info(client, headers, {})

    async def _manage_playlists(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any]) -> ToolResult:
        action = args.get("action", "").lower()

        if action == "list":
            resp = await client.get(
                f"{YOUTUBE_BASE_URL}/playlists",
                headers=headers,
                params={"part": "snippet,contentDetails", "mine": "true", "maxResults": 25},
            )
            if resp.status_code >= 400:
                return ToolResult.error(f"Failed to list playlists ({resp.status_code}): {resp.text}")

            items = resp.json().get("items", [])
            if not items:
                return ToolResult.success("No playlists found in your YouTube channel.")

            lines = [f"Found {len(items)} playlist(s):"]
            for pl in items:
                pid = pl.get("id")
                title = pl.get("snippet", {}).get("title")
                count = pl.get("contentDetails", {}).get("itemCount", 0)
                lines.append(f"• [{pid}] {title} ({count} videos)")
            return ToolResult.success("\n".join(lines))

        elif action == "create":
            title = args.get("title", "New Playlist")
            desc = args.get("description", "")
            payload = {
                "snippet": {"title": title, "description": desc},
                "status": {"privacyStatus": "private"},
            }
            resp = await client.post(
                f"{YOUTUBE_BASE_URL}/playlists",
                headers=headers,
                params={"part": "snippet,status"},
                json=payload,
            )
            if resp.status_code >= 400:
                return ToolResult.error(f"Failed to create playlist ({resp.status_code}): {resp.text}")

            created = resp.json()
            return ToolResult.success(f"Playlist '{title}' created successfully. Playlist ID: {created.get('id')}")

        elif action == "add_video":
            playlist_id = args.get("playlist_id")
            video_id = args.get("video_id")
            if not playlist_id or not video_id:
                return ToolResult.error("Must specify 'playlist_id' and 'video_id'.")

            payload = {
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            }
            resp = await client.post(
                f"{YOUTUBE_BASE_URL}/playlistItems",
                headers=headers,
                params={"part": "snippet"},
                json=payload,
            )
            if resp.status_code >= 400:
                return ToolResult.error(f"Failed to add video to playlist ({resp.status_code}): {resp.text}")

            return ToolResult.success(f"Added video '{video_id}' to playlist '{playlist_id}' successfully.")

        return ToolResult.error(f"Unknown playlist action '{action}'. Supported: 'list', 'create', 'add_video'.")

    async def _upload_video(self, client: httpx.AsyncClient, headers: dict[str, str], args: dict[str, Any], context: ExecutionContext) -> ToolResult:
        rel_path = args.get("local_path", "")
        target_path = context.sandbox.validate_path_access(rel_path, is_write=False)

        if not target_path.is_file():
            return ToolResult.error(f"Local video file '{rel_path}' does not exist.")

        title = args.get("title", target_path.stem)
        desc = args.get("description", "")
        tags = args.get("tags", [])
        privacy = args.get("privacy_status", "private")

        metadata: dict[str, Any] = {
            "snippet": {
                "title": title,
                "description": desc,
                "tags": tags,
                "categoryId": "22",  # People & Blogs default
            },
            "status": {
                "privacyStatus": privacy,
            },
        }

        with open(target_path, "rb") as f:
            video_bytes = f.read()

        files = {
            "data": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
            "file": (target_path.name, video_bytes, "video/*"),
        }

        resp = await client.post(YOUTUBE_UPLOAD_URL, headers=headers, files=files)
        if resp.status_code >= 400:
            return ToolResult.error(f"YouTube upload failed ({resp.status_code}): {resp.text}")

        res_data = resp.json()
        vid = res_data.get("id", "unknown")
        status = res_data.get("status", {}).get("uploadStatus", "uploaded")
        return ToolResult.success(
            f"Video '{title}' successfully uploaded to YouTube!\n"
            f"• Video ID    : {vid}\n"
            f"• Status      : {status}\n"
            f"• Privacy     : {privacy}\n"
            f"• URL         : https://youtu.be/{vid}"
        )
