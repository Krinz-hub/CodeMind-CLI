"""OAuth 2.0 PKCE lifecycle, token exchange, and credential management."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from codemind.connectors.models import AuthMethod, ConnectorCredential
from codemind.connectors.vault import CredentialVault


class OAuthError(Exception):
    """Exception raised during OAuth 2.0 authentication flows."""
    pass


class OAuthManager:
    """Manages RFC 7636 PKCE parameters, state tokens, and HTTP token exchanges."""

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        """Generate (code_verifier, code_challenge) using SHA-256."""
        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return verifier, challenge

    @staticmethod
    def generate_state() -> str:
        """Generate a random state token for CSRF protection."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def build_authorization_url(
        auth_endpoint: str,
        client_id: str,
        redirect_uri: str,
        scopes: list[str],
        state: str,
        code_challenge: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> str:
        """Construct the complete OAuth 2.0 authorization URL."""
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        if extra_params:
            params.update(extra_params)

        query = urlencode(params)
        delimiter = "&" if "?" in auth_endpoint else "?"
        return f"{auth_endpoint}{delimiter}{query}"

    @staticmethod
    async def exchange_code(
        token_endpoint: str,
        client_id: str,
        code: str,
        redirect_uri: str,
        client_secret: str | None = None,
        code_verifier: str | None = None,
    ) -> dict[str, Any]:
        """Exchange an authorization code for an access token (and optional refresh token)."""
        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
        }
        if client_secret:
            data["client_secret"] = client_secret
        if code_verifier:
            data["code_verifier"] = code_verifier

        headers = {"Accept": "application/json"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(token_endpoint, data=data, headers=headers)
            if resp.status_code >= 400:
                raise OAuthError(f"Token exchange failed ({resp.status_code}): {resp.text}")
            return resp.json()

    @staticmethod
    async def refresh_access_token(
        token_endpoint: str,
        client_id: str,
        refresh_token: str,
        client_secret: str | None = None,
    ) -> dict[str, Any]:
        """Obtain a fresh access token using a stored refresh token."""
        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        }
        if client_secret:
            data["client_secret"] = client_secret

        headers = {"Accept": "application/json"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(token_endpoint, data=data, headers=headers)
            if resp.status_code >= 400:
                raise OAuthError(f"Token refresh failed ({resp.status_code}): {resp.text}")
            return resp.json()

    @staticmethod
    async def revoke_token(
        revoke_endpoint: str,
        token: str,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> bool:
        """Revoke an active access or refresh token at the provider endpoint."""
        data: dict[str, str] = {"token": token}
        if client_id:
            data["client_id"] = client_id
        if client_secret:
            data["client_secret"] = client_secret

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(revoke_endpoint, data=data)
            return resp.status_code < 400


class ConnectorAuthManager:
    """Coordinates authentication state, automatic token refreshing, and storage for connectors."""

    def __init__(self, vault: CredentialVault):
        self.vault = vault

    async def get_valid_access_token(
        self,
        connector_id: str,
        token_endpoint: str | None = None,
    ) -> str | None:
        """Retrieve a valid, unexpired access token, automatically refreshing if necessary."""
        cred = self.vault.get_credential(connector_id)
        if not cred:
            return None

        # API key or bot token doesn't expire via OAuth flow
        if cred.auth_method in (AuthMethod.API_KEY, AuthMethod.BOT_TOKEN):
            return cred.api_key or cred.access_token

        # Unexpired access token
        if not cred.is_expired and cred.access_token:
            return cred.access_token

        # Expired but has refresh token
        if cred.refresh_token and token_endpoint and cred.client_id:
            try:
                refreshed = await OAuthManager.refresh_access_token(
                    token_endpoint=token_endpoint,
                    client_id=cred.client_id,
                    refresh_token=cred.refresh_token,
                    client_secret=cred.client_secret,
                )
                new_token = refreshed.get("access_token")
                expires_in = refreshed.get("expires_in")
                new_expiry = (time.time() + float(expires_in)) if expires_in else None

                cred.access_token = new_token
                if new_expiry:
                    cred.expires_at = new_expiry
                if "refresh_token" in refreshed:
                    cred.refresh_token = refreshed["refresh_token"]

                self.vault.store_credential(cred)
                return new_token
            except Exception:
                return None

        return cred.access_token
