"""Secure encrypted credential vault for OAuth tokens and API keys."""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any

from cryptography.fernet import Fernet

from codemind.connectors.models import AuthMethod, ConnectorCredential


class CredentialVaultError(Exception):
    """Base exception for CredentialVault operations."""
    pass


class CredentialVault:
    """Manages encrypted credential persistence using SQLite and Fernet (AES-128-CBC + HMAC-SHA256)."""

    def __init__(self, db_path: Path | None = None, key_file: Path | None = None):
        home_cm = Path.home() / ".codemind"
        home_cm.mkdir(parents=True, exist_ok=True)

        self.db_path = (db_path or (home_cm / "vault.db")).resolve()
        self.key_file = (key_file or (home_cm / ".vault_key")).resolve()
        self._fernet: Fernet | None = None

        self._init_encryption()
        self._init_db()

    def _init_encryption(self) -> None:
        """Initialize or load master encryption key with 0o600 permissions."""
        if self.key_file.is_file():
            try:
                key = self.key_file.read_bytes().strip()
                self._fernet = Fernet(key)
                return
            except Exception:
                pass

        # Generate new key
        new_key = Fernet.generate_key()
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        # Write with restricted permissions
        fd = os.open(str(self.key_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with open(fd, "wb") as f:
            f.write(new_key)
        self._fernet = Fernet(new_key)

    def _init_db(self) -> None:
        """Ensure credentials table exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS credentials (
                    connector_id TEXT PRIMARY KEY,
                    auth_method TEXT NOT NULL,
                    encrypted_payload BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at REAL
                );
            """)
            conn.commit()

    def store_credential(self, cred: ConnectorCredential) -> None:
        """Encrypt and persist credential bundle."""
        if not self._fernet:
            raise CredentialVaultError("Vault encryption not initialized.")

        payload_json = cred.model_dump_json()
        encrypted = self._fernet.encrypt(payload_json.encode("utf-8"))
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO credentials (connector_id, auth_method, encrypted_payload, created_at, updated_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(connector_id) DO UPDATE SET
                    auth_method = excluded.auth_method,
                    encrypted_payload = excluded.encrypted_payload,
                    updated_at = excluded.updated_at,
                    expires_at = excluded.expires_at;
            """, (cred.connector_id, cred.auth_method.value, encrypted, now_iso, now_iso, cred.expires_at))
            conn.commit()

    def get_credential(self, connector_id: str) -> ConnectorCredential | None:
        """Retrieve and decrypt credential bundle."""
        if not self._fernet:
            raise CredentialVaultError("Vault encryption not initialized.")

        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT encrypted_payload FROM credentials WHERE connector_id = ?;",
                (connector_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        encrypted = row[0]
        try:
            decrypted = self._fernet.decrypt(encrypted).decode("utf-8")
            data = json.loads(decrypted)
            return ConnectorCredential.model_validate(data)
        except Exception as ex:
            raise CredentialVaultError(f"Failed to decrypt credential for '{connector_id}': {ex}") from ex

    def delete_credential(self, connector_id: str) -> bool:
        """Remove credential bundle from vault."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM credentials WHERE connector_id = ?;", (connector_id,))
            conn.commit()
            return cursor.rowcount > 0

    def list_credentials(self) -> list[dict[str, Any]]:
        """List stored credentials metadata without leaking plaintext secrets."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT connector_id, auth_method, updated_at, expires_at
                FROM credentials
                ORDER BY connector_id;
            """)
            rows = cursor.fetchall()

        now = time.time()
        results: list[dict[str, Any]] = []
        for r in rows:
            cid, method, updated_at, expires_at = r
            is_expired = (expires_at is not None and now >= expires_at)
            results.append({
                "connector_id": cid,
                "auth_method": method,
                "is_expired": is_expired,
                "expires_at": expires_at,
                "updated_at": updated_at,
                "status": "EXPIRED" if is_expired else "STORED",
            })
        return results

    def is_authenticated(self, connector_id: str) -> bool:
        """Check if an active, usable credential exists for the connector."""
        cred = self.get_credential(connector_id)
        if not cred:
            return False
        if cred.auth_method == AuthMethod.API_KEY and cred.api_key:
            return True
        if cred.auth_method == AuthMethod.BOT_TOKEN and (cred.api_key or cred.access_token):
            return True
        if cred.auth_method == AuthMethod.OAUTH2:
            return bool(cred.access_token or cred.refresh_token)
        return False
