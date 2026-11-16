# Connector Ecosystem Testing Strategy & Verification Report

## 1. Hermetic Testing Policy

All tests in CodeMind CLI run in completely offline, hermetic environments:
- **No real cloud egress**: Tests do not make network calls to Google, Slack, Discord, Notion, or Spotify.
- **Provider Mocking**: HTTP requests are mocked using `unittest.mock.patch("httpx.AsyncClient...")`.
- **Distinction between mocked and real connectivity**: Mocked tests prove schema adherence, error handling, state machine transitions, and permission enforcement. They are **not** claimed as proof of real live provider credentials.
- **Integration Tests**: Live integration against production APIs is supported only when explicit test credentials (e.g. `GOOGLE_CLIENT_ID`, `NOTION_TOKEN`) are configured in the environment.

---

## 2. Test Suite Architecture (`tests/connectors/`)

The connector test suite comprises 31 dedicated unit and integration tests across 5 test modules:

| Test File | Tests | Focus Areas |
|---|---|---|
| `test_vault_and_auth.py` | 6 | Fernet encryption at rest, key permission `0o600`, RFC 7636 PKCE pair generation, CSRF state generation, automatic token refresh, secret scrubbing. |
| `test_permissions_and_tools.py` | 6 | Manifest validation, ConnectorRegistry, enable/disable policy, read-only mode, dynamic Pydantic schema generation, user approval workflows on `SENSITIVE` actions, tool registry integration. |
| `test_native_connectors.py` | 9 | Mocked API interactions for Gmail, Google Drive, Google Calendar, YouTube, Discord, Slack, Notion, Spotify; HTTPStatusError handling and false-success prevention. |
| `test_mcp_streamable.py` | 3 | Streamable HTTP and SSE MCP servers, tool discovery, RPC execution, untrusted data description scrubbing. |
| `test_connectors_cli.py` | 7 | CLI commands: `list`, `search`, `inspect`, `connect`, `disconnect`, `permissions`, `tools`, and `codemind mcp` lifecycle (`add`, `list`, `inspect`, `remove`). |

---

## 3. Executing the Test Suite

Run the full hermetic test suite (191 tests):
```bash
uv run --python 3.12 python run_tests.py
```

Run only connector tests:
```bash
uv run --python 3.12 python -m unittest discover -s tests/connectors -p "test_*.py"
```

Run CLI command tests:
```bash
uv run --python 3.12 python -m unittest tests/connectors/test_connectors_cli.py
```
