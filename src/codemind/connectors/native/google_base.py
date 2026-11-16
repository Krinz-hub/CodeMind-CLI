"""Shared Google OAuth and REST foundation for Google application connectors."""

from __future__ import annotations

import time
from typing import Any
import httpx

from codemind.connectors.base import ConnectorAdapter
from codemind.connectors.models import ConnectionStatus, ConnectorHealth
from codemind.tools.base import ToolResult


GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleBaseConnector(ConnectorAdapter):
    """Shared foundation for Gmail, Google Drive, Google Calendar, and YouTube connectors."""

    async def get_auth_headers(self) -> dict[str, str]:
        """Obtain valid bearer authorization headers, refreshing token if expired."""
        token = await self.auth_manager.get_valid_access_token(
            self.connector_id,
            token_endpoint=GOOGLE_TOKEN_ENDPOINT,
        )
        if not token:
            raise PermissionError(
                f"Connector '{self.connector_id}' is not authenticated. Please run 'codemind connectors connect {self.connector_id}'."
            )
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    async def check_health(self) -> ConnectorHealth:
        """Verify token validity by probing the Google OAuth2 userinfo endpoint."""
        if not self.is_connected():
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.DISCONNECTED,
                message=f"Connector '{self.connector_id}' has no stored credentials in the vault.",
            )

        t0 = time.time()
        try:
            headers = await self.get_auth_headers()
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(GOOGLE_USERINFO_ENDPOINT, headers=headers)
                latency_ms = (time.time() - t0) * 1000.0

                if resp.status_code == 200:
                    data = resp.json()
                    email = data.get("email", "authorized-user")
                    return ConnectorHealth(
                        healthy=True,
                        status=ConnectionStatus.CONNECTED,
                        message=f"Connected as Google user '{email}'.",
                        latency_ms=round(latency_ms, 2),
                        details={"email": email, "sub": data.get("sub")},
                    )
                elif resp.status_code == 401:
                    return ConnectorHealth(
                        healthy=False,
                        status=ConnectionStatus.EXPIRED,
                        message="Google credentials have expired or were revoked.",
                        latency_ms=round(latency_ms, 2),
                    )
                else:
                    return ConnectorHealth(
                        healthy=False,
                        status=ConnectionStatus.ERROR,
                        message=f"Google API responded with HTTP {resp.status_code}: {resp.text}",
                        latency_ms=round(latency_ms, 2),
                    )
        except Exception as ex:
            latency_ms = (time.time() - t0) * 1000.0
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.ERROR,
                message=f"Health check failed: {ex}",
                latency_ms=round(latency_ms, 2),
            )
