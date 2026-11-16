"""Official Spotify Web API connector (Phase 2)."""

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


SPOTIFY_BASE_URL = "https://api.spotify.com/v1"


class SpotifyConnector(ConnectorAdapter):
    """Integrates official Spotify Web API for search, playlist management, and playback controls."""

    manifest = ConnectorManifest(
        connector_id="spotify",
        name="Spotify",
        description="Search music tracks and albums, inspect and manage playlists, and trigger playback controls.",
        category="media",
        version="1.0.0",
        icon="🎵",
        auth_method=AuthMethod.OAUTH2,
        required_scopes=[
            "playlist-read-private",
            "playlist-modify-public",
            "playlist-modify-private",
            "user-modify-playback-state",
            "user-read-playback-state",
        ],
        actions=[
            ConnectorAction(
                name="search",
                description="Search Spotify music catalog for tracks, albums, or artists.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query keywords or song title"},
                        "search_type": {"type": "string", "description": "Item type: 'track', 'album', 'artist', or comma-separated", "default": "track,album"},
                        "limit": {"type": "integer", "description": "Max items to return (max 50)", "default": 20},
                    },
                    "required": ["query"],
                },
            ),
            ConnectorAction(
                name="get_playlists",
                description="List current user's Spotify playlists.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max playlists to return", "default": 20},
                    },
                },
            ),
            ConnectorAction(
                name="create_playlist",
                description="Create a new playlist in the user's Spotify library (WRITE).",
                risk_level=ActionRiskLevel.WRITE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Playlist title"},
                        "description": {"type": "string", "description": "Optional playlist description", "default": ""},
                        "public": {"type": "boolean", "description": "Whether playlist is public", "default": False},
                    },
                    "required": ["name"],
                },
            ),
            ConnectorAction(
                name="manage_tracks",
                description="Add or remove tracks from a Spotify playlist (WRITE).",
                risk_level=ActionRiskLevel.WRITE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "playlist_id": {"type": "string", "description": "Target Spotify playlist ID"},
                        "action": {"type": "string", "description": "Operation: 'add' or 'remove'", "default": "add"},
                        "uris": {"type": "string", "description": "Comma-separated track URIs (e.g. 'spotify:track:4cOdK2wGLETKBW3PvgPWqT')"},
                    },
                    "required": ["playlist_id", "uris"],
                },
            ),
            ConnectorAction(
                name="playback_control",
                description="Control active Spotify playback: play, pause, next, or previous (SENSITIVE: requires human approval).",
                risk_level=ActionRiskLevel.SENSITIVE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "Playback command: 'play', 'pause', 'next', or 'previous'", "default": "play"},
                        "device_id": {"type": "string", "description": "Optional target device ID"},
                    },
                    "required": ["action"],
                },
            ),
        ],
    )

    async def get_auth_headers(self) -> dict[str, str]:
        token = await self.auth_manager.get_valid_access_token(self.connector_id)
        if not token:
            raise PermissionError("Spotify OAuth credentials not configured. Run 'codemind connectors connect spotify'.")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def check_health(self) -> ConnectorHealth:
        if not self.is_connected():
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.DISCONNECTED,
                message="Spotify account is not connected.",
            )

        t0 = time.time()
        try:
            headers = await self.get_auth_headers()
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{SPOTIFY_BASE_URL}/me", headers=headers)
                latency = (time.time() - t0) * 1000

                if res.status_code == 200:
                    data = res.json()
                    user_name = data.get("display_name") or data.get("id") or "Spotify User"
                    return ConnectorHealth(
                        healthy=True,
                        status=ConnectionStatus.CONNECTED,
                        message=f"Connected to Spotify as '{user_name}' ({data.get('product', 'free')} plan)",
                        latency_ms=round(latency, 2),
                    )
                elif res.status_code in (401, 403):
                    return ConnectorHealth(
                        healthy=False,
                        status=ConnectionStatus.EXPIRED,
                        message="Spotify authorization expired or revoked.",
                    )
                else:
                    return ConnectorHealth(
                        healthy=False,
                        status=ConnectionStatus.ERROR,
                        message=f"Spotify API returned HTTP {res.status_code}: {res.text[:120]}",
                    )
        except Exception as e:
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.ERROR,
                message=f"Spotify connection failure: {str(e)}",
            )

    async def execute_action(
        self,
        action_name: str,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        dispatch = {
            "search": self._action_search,
            "get_playlists": self._action_get_playlists,
            "create_playlist": self._action_create_playlist,
            "manage_tracks": self._action_manage_tracks,
            "playback_control": self._action_playback_control,
        }

        handler = dispatch.get(action_name)
        if not handler:
            return ToolResult.error(f"Unknown action '{action_name}' for Spotify connector.")

        try:
            return await handler(params, context)
        except httpx.HTTPStatusError as e:
            err_msg = f"Spotify API error (HTTP {e.response.status_code}): {e.response.text[:200]}"
            return ToolResult.error(err_msg, metadata={"status_code": e.response.status_code})
        except Exception as e:
            return ToolResult.error(f"Spotify action failed: {str(e)}")

    async def _action_search(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        query = params.get("query", "").strip()
        search_type = params.get("search_type", "track,album")
        limit = min(int(params.get("limit", 20)), 50)

        if not query:
            return ToolResult.error("Parameter 'query' is required.")

        headers = await self.get_auth_headers()
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                f"{SPOTIFY_BASE_URL}/search",
                headers=headers,
                params={"q": query, "type": search_type, "limit": limit},
            )
            res.raise_for_status()
            data = res.json()

        results: dict[str, Any] = {}
        summary_lines = []

        if "tracks" in data:
            tracks = []
            for t in data["tracks"].get("items", []):
                artists = ", ".join(a.get("name", "") for a in t.get("artists", []))
                tracks.append({
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "artists": artists,
                    "album": t.get("album", {}).get("name"),
                    "uri": t.get("uri"),
                    "duration_ms": t.get("duration_ms"),
                })
            results["tracks"] = tracks
            summary_lines.append(f"Tracks ({len(tracks)}):")
            for trk in tracks[:5]:
                summary_lines.append(f"  • {trk['name']} - {trk['artists']} ({trk['uri']})")

        if "albums" in data:
            albums = []
            for a in data["albums"].get("items", []):
                artists = ", ".join(art.get("name", "") for art in a.get("artists", []))
                albums.append({
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "artists": artists,
                    "release_date": a.get("release_date"),
                    "uri": a.get("uri"),
                })
            results["albums"] = albums
            summary_lines.append(f"Albums ({len(albums)}):")
            for alb in albums[:5]:
                summary_lines.append(f"  • {alb['name']} - {alb['artists']} ({alb['uri']})")

        summary_text = "\n".join(summary_lines) if summary_lines else "No matching items found."
        return ToolResult.success(
            f"Spotify Search Results for '{query}':\n{summary_text}",
            metadata=results,
        )

    async def _action_get_playlists(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        limit = min(int(params.get("limit", 20)), 50)
        headers = await self.get_auth_headers()

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                f"{SPOTIFY_BASE_URL}/me/playlists",
                headers=headers,
                params={"limit": limit},
            )
            res.raise_for_status()
            data = res.json()

        playlists = []
        for pl in data.get("items", []):
            playlists.append({
                "id": pl.get("id"),
                "name": pl.get("name"),
                "total_tracks": pl.get("tracks", {}).get("total", 0),
                "public": pl.get("public"),
                "uri": pl.get("uri"),
            })

        return ToolResult.success(
            f"Retrieved {len(playlists)} playlists from Spotify:\n"
            + json.dumps(playlists, indent=2),
            metadata={"playlists": playlists, "total": len(playlists)},
        )

    async def _action_create_playlist(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        name = params.get("name", "").strip()
        description = params.get("description", "")
        public = bool(params.get("public", False))

        if not name:
            return ToolResult.error("Parameter 'name' is required.")

        headers = await self.get_auth_headers()
        async with httpx.AsyncClient(timeout=15.0) as client:
            # First fetch current user ID
            me_res = await client.get(f"{SPOTIFY_BASE_URL}/me", headers=headers)
            me_res.raise_for_status()
            user_id = me_res.json().get("id")

            # Create playlist
            payload = {
                "name": name,
                "description": description,
                "public": public,
            }
            res = await client.post(
                f"{SPOTIFY_BASE_URL}/users/{user_id}/playlists",
                headers=headers,
                json=payload,
            )
            res.raise_for_status()
            data = res.json()

        return ToolResult.success(
            f"Spotify playlist '{name}' created successfully.\nID: {data.get('id')}\nURI: {data.get('uri')}",
            metadata={"id": data.get("id"), "uri": data.get("uri"), "name": name},
        )

    async def _action_manage_tracks(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        playlist_id = params.get("playlist_id", "").strip()
        action = params.get("action", "add").lower()
        uris_raw = params.get("uris", "")

        if not playlist_id:
            return ToolResult.error("Parameter 'playlist_id' is required.")

        uris = [u.strip() for u in uris_raw.split(",") if u.strip()]
        if not uris:
            return ToolResult.error("Parameter 'uris' must contain at least one track URI.")

        headers = await self.get_auth_headers()
        async with httpx.AsyncClient(timeout=15.0) as client:
            if action == "add":
                res = await client.post(
                    f"{SPOTIFY_BASE_URL}/playlists/{playlist_id}/tracks",
                    headers=headers,
                    json={"uris": uris},
                )
                res.raise_for_status()
                data = res.json()
                return ToolResult.success(
                    f"Added {len(uris)} track(s) to Spotify playlist '{playlist_id}'. Snapshot ID: {data.get('snapshot_id')}",
                    metadata={"snapshot_id": data.get("snapshot_id")},
                )
            elif action == "remove":
                tracks_body = [{"uri": u} for u in uris]
                res = await client.request(
                    "DELETE",
                    f"{SPOTIFY_BASE_URL}/playlists/{playlist_id}/tracks",
                    headers=headers,
                    json={"tracks": tracks_body},
                )
                res.raise_for_status()
                data = res.json()
                return ToolResult.success(
                    f"Removed {len(uris)} track(s) from Spotify playlist '{playlist_id}'. Snapshot ID: {data.get('snapshot_id')}",
                    metadata={"snapshot_id": data.get("snapshot_id")},
                )
            else:
                return ToolResult.error(f"Invalid manage_tracks action '{action}'. Must be 'add' or 'remove'.")

    async def _action_playback_control(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        action = params.get("action", "play").lower().strip()
        device_id = params.get("device_id")

        headers = await self.get_auth_headers()
        query_params = {}
        if device_id:
            query_params["device_id"] = device_id

        async with httpx.AsyncClient(timeout=15.0) as client:
            if action == "play":
                res = await client.put(f"{SPOTIFY_BASE_URL}/me/player/play", headers=headers, params=query_params)
            elif action == "pause":
                res = await client.put(f"{SPOTIFY_BASE_URL}/me/player/pause", headers=headers, params=query_params)
            elif action == "next":
                res = await client.post(f"{SPOTIFY_BASE_URL}/me/player/next", headers=headers, params=query_params)
            elif action == "previous":
                res = await client.post(f"{SPOTIFY_BASE_URL}/me/player/previous", headers=headers, params=query_params)
            else:
                return ToolResult.error(f"Unsupported playback action '{action}'. Use play, pause, next, or previous.")

            # Note: Spotify playback endpoints return 204 No Content on success
            if res.status_code in (200, 204):
                return ToolResult.success(f"Spotify playback command '{action}' dispatched successfully.")
            elif res.status_code == 404:
                return ToolResult.error("No active Spotify playback device found. Start playback on your Spotify app first.")
            else:
                res.raise_for_status()
                return ToolResult.success(f"Spotify command '{action}' processed.")
