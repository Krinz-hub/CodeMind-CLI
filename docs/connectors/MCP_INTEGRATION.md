# Model Context Protocol (MCP) Client Integration

## 1. Overview

CodeMind CLI acts as a first-class Model Context Protocol (MCP) client. External tools and resources hosted by local processes or remote servers can be seamlessly integrated into CodeMind's autonomous agent loop.

Supported transport protocols:
1. **`stdio`**: Standard input/output pipes with local child processes (e.g. `npx`, `python -m`, custom binaries).
2. **`sse`**: Server-Sent Events streamable transport over HTTP.
3. **`http`**: Stateless or streaming HTTP JSON-RPC endpoint.

---

## 2. Server Configuration (`.codemind/mcp.json`)

MCP servers are configured in the workspace configuration file `.codemind/mcp.json`:

```json
{
  "mcpServers": {
    "sqlite": {
      "name": "sqlite",
      "transport": "stdio",
      "command": "python",
      "args": ["-m", "mcp_server_sqlite", "--db-path", "data/app.db"],
      "disabled": false
    },
    "github-remote": {
      "name": "github-remote",
      "transport": "http",
      "url": "https://api.github-mcp.internal/rpc",
      "headers": {
        "Authorization": "Bearer gh_token_redacted"
      },
      "disabled": false,
      "timeout_seconds": 30,
      "max_reconnect_attempts": 3
    }
  }
}
```

---

## 3. CLI Management Commands

Manage configured MCP servers directly from the terminal:

```bash
# List all configured servers and status
codemind mcp list

# Add a local stdio MCP server
codemind mcp add sqlite python --arg -m --arg mcp_server_sqlite

# Add a remote HTTP/SSE MCP server
codemind mcp add remote-docs https://mcp.company.internal/tools --transport http --header "Authorization:Bearer token"

# Inspect server details, working directory, and environment
codemind mcp inspect sqlite

# Test connectivity and tool discovery
codemind mcp test sqlite

# Remove server from configuration
codemind mcp remove sqlite
```

Interactive REPL slash command support:
```text
/mcp list
/mcp add <name> <command> [args...]
/mcp disable <name>
/mcp enable <name>
/mcp remove <name>
```

---

## 4. MCP Tool Discovery and Security Isolation

1. **Untrusted Data Sanitization**: External MCP servers are treated as untrusted third parties. Descriptions, names, and returned payloads are passed through `redact_secrets()` to strip credentials and injection patterns. Returned data is formatted strictly as tool output, never injected into system instructions.
2. **Dynamic Namespace Isolation**: Discovered MCP tools are registered with prefix `mcp__<server_name>__<tool_name>` to eliminate name collision with built-in agent tools.
3. **Automatic Reconnection & Resilience**: If an HTTP or SSE connection drops during execution, `MCPClient` executes exponential-backoff retries up to `max_reconnect_attempts`.
4. **Non-Blocking Agent Initialization**: If an MCP server fails to start or encounters an unhandled exception, the error is isolated and logged; it never crashes or halts the CodeMind companion agent.
