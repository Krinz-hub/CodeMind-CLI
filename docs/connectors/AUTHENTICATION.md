# Authentication and Credential Lifecycle Architecture

## 1. Authentication Mechanisms

CodeMind supports four standardized authentication paradigms across its universal connectors:

| Method | Description | Used By |
|---|---|---|
| `OAUTH2` | OAuth 2.0 Authorization Code Flow with PKCE (RFC 7636) | YouTube, Gmail, Google Drive, Google Calendar, Spotify |
| `API_KEY` | Long-lived secret or workspace integration token | Notion |
| `BOT_TOKEN` | Bot identity token | Discord, Slack |
| `NONE` | Public or unauthenticated read-only services | Public registries |

---

## 2. OAuth 2.0 PKCE Foundation

OAuth 2.0 implementations in CodeMind strictly follow RFC 7636 (Proof Key for Public Client Exchange):

1. **Code Verifier & Challenge**:
   - `code_verifier`: 64 bytes of cryptographically random URL-safe characters (`secrets.token_urlsafe(64)`).
   - `code_challenge`: SHA-256 digest of verifier, Base64-URL encoded with padding stripped (`code_challenge_method=S256`).
2. **State & CSRF Defense**:
   - High-entropy single-use state token (`secrets.token_urlsafe(32)`).
   - Validated upon return and immediately purged to prevent replay and CSRF attacks.
3. **Least Privilege Scopes**:
   - Connectors request only the minimum granular scopes necessary to perform their declared actions.
   - Example: YouTube requests `https://www.googleapis.com/auth/youtube.readonly` and `upload`, but never general Google account scopes.
4. **Token Refresh Cycle**:
   - When an access token expires (`expires_at < time.time()`), `ConnectorAuthManager.get_valid_access_token()` automatically invokes `OAuthManager.refresh_access_token()` using the stored refresh token.
   - The new token and expiry are re-encrypted and persisted to `CredentialVault`.

---

## 3. Cryptographic Storage: `CredentialVault`

CodeMind does **not** store plaintext tokens in `.json`, `.yaml`, or `.env` files.

### 3.1 Vault Key Management
- Key location: `.codemind/.vault_key`
- File mode: `0o600` (strictly POSIX user read/write only).
- Algorithm: Fernet symmetric encryption specification (AES-128 in CBC mode with PKCS7 padding and HMAC using SHA-256 for authenticated encryption).

### 3.2 Vault Database
- SQLite database at `.codemind/vault.db`.
- Schema:
  ```sql
  CREATE TABLE IF NOT EXISTS credentials (
      connector_id TEXT PRIMARY KEY,
      auth_method TEXT NOT NULL,
      encrypted_payload BLOB NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      expires_at REAL
  );
  ```
- All access tokens, refresh tokens, client secrets, and custom metadata are encapsulated inside `encrypted_payload`.

---

## 4. Disconnection and Revocation

When a user executes `codemind connectors disconnect <connector_id>`:
1. If the provider exposes an RFC 7009 revocation endpoint (e.g. `https://oauth2.googleapis.com/revoke`), the connector issues an async POST request to revoke the token upstream.
2. The credential record is permanently deleted from the SQLite vault.
3. Associated memory buffers and cached adapter instances are cleared.
