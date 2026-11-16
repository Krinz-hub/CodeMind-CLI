"""Unit tests for CredentialVault, OAuth PKCE, Token Refresh, and Redaction."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from codemind.connectors.auth import ConnectorAuthManager, OAuthManager
from codemind.connectors.models import (
    ActionRiskLevel,
    AuthMethod,
    ConnectionStatus,
    ConnectorCredential,
)
from codemind.connectors.vault import CredentialVault
from codemind.security.redaction import redact_secrets


class TestVaultAndAuth(unittest.TestCase):
    """Hermetic tests for encrypted vault storage and OAuth flows."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.temp_dir.name)
        self.db_path = self.workspace_root / ".codemind" / "vault.db"
        self.key_file = self.workspace_root / ".codemind" / ".vault_key"
        self.vault = CredentialVault(db_path=self.db_path, key_file=self.key_file)
        self.auth = ConnectorAuthManager(self.vault)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_key_file_permissions(self):
        """Verify the encryption key file is restricted to user-only read/write (0o600)."""
        self.assertTrue(self.key_file.exists())
        file_stat = os.stat(self.key_file)
        mode = stat.S_IMODE(file_stat.st_mode)
        self.assertEqual(mode, 0o600)

    def test_credential_encryption_and_decryption(self):
        """Verify plaintext tokens are encrypted at rest in SQLite and decrypted correctly."""
        cred = ConnectorCredential(
            connector_id="gmail",
            auth_method=AuthMethod.OAUTH2,
            access_token="ya29.secret_test_token_12345",
            refresh_token="1//refresh_token_xyz987",
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )
        self.vault.store_credential(cred)

        # Inspect raw database bytes to ensure token is encrypted at rest
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT encrypted_payload FROM credentials WHERE connector_id = 'gmail'")
        row = cur.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        encrypted_payload = row[0]
        self.assertNotIn(b"ya29.secret_test_token_12345", encrypted_payload)
        self.assertNotIn(b"1//refresh_token_xyz987", encrypted_payload)

        # Retrieve through vault decryptor
        loaded = self.vault.get_credential("gmail")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.access_token, "ya29.secret_test_token_12345")
        self.assertEqual(loaded.refresh_token, "1//refresh_token_xyz987")
        self.assertEqual(loaded.scopes, ["https://www.googleapis.com/auth/gmail.readonly"])

    def test_delete_and_revoke_credential(self):
        """Verify deleting credentials removes them cleanly from vault."""
        cred = ConnectorCredential(
            connector_id="slack",
            auth_method=AuthMethod.BOT_TOKEN,
            access_token="xoxb-secret-token",
        )
        self.vault.store_credential(cred)
        self.assertIsNotNone(self.vault.get_credential("slack"))

        deleted = self.vault.delete_credential("slack")
        self.assertTrue(deleted)
        self.assertIsNone(self.vault.get_credential("slack"))

    def test_pkce_generation_and_state_validation(self):
        """Verify RFC 7636 PKCE pair generation and state string creation."""
        verifier, challenge = OAuthManager.generate_pkce_pair()
        self.assertGreater(len(verifier), 40)
        self.assertGreater(len(challenge), 40)
        self.assertNotEqual(verifier, challenge)

        state = OAuthManager.generate_state()
        self.assertGreater(len(state), 20)

    @patch("httpx.AsyncClient.post")
    def test_token_refresh_flow(self, mock_post):
        """Verify OAuthManager refreshes expired access token using refresh token."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "ya29.new_refreshed_access_token_456",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        mock_resp.raise_for_status = lambda: None
        mock_post.return_value = mock_resp

        # Prepopulate expired token in vault
        expired_cred = ConnectorCredential(
            connector_id="youtube",
            auth_method=AuthMethod.OAUTH2,
            access_token="ya29.expired_token",
            refresh_token="1//refresh_valid",
            client_id="yt_client",
            client_secret="yt_secret",
            expires_at=100.0,  # Expired long ago
        )
        self.vault.store_credential(expired_cred)

        import asyncio
        new_token = asyncio.run(
            self.auth.get_valid_access_token("youtube", token_endpoint="https://oauth2.googleapis.com/token")
        )

        self.assertEqual(new_token, "ya29.new_refreshed_access_token_456")
        updated_cred = self.vault.get_credential("youtube")
        self.assertEqual(updated_cred.access_token, "ya29.new_refreshed_access_token_456")
        self.assertGreater(updated_cred.expires_at, 1000.0)

    def test_secret_redaction(self):
        """Verify tokens, API keys, and Authorization headers are redacted."""
        log_sample = (
            "Connecting with Bearer ya29.a0AfH6SMB_secret_oauth_string_12345 "
            "and Discord Bot MTIzNDU2Nzg5MTIzNDU2Nzg5MDEy.abcdef.ghijklmnopqrstu12345 "
            "and OpenAI sk-proj-1234567890abcdef1234567890abcdef"
        )
        redacted = redact_secrets(log_sample)
        self.assertNotIn("ya29.a0AfH6SMB_secret_oauth_string_12345", redacted)
        self.assertNotIn("sk-proj-1234567890abcdef1234567890abcdef", redacted)
        self.assertIn("[REDACTED_OPENAI_KEY]", redacted)


if __name__ == "__main__":
    unittest.main()
