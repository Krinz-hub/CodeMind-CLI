# Model Context Protocol (MCP) Integration: CodeMind CLI

## 1. Overview & Strategy

The Model Context Protocol (MCP) provides a standardized protocol for integrating external tool servers (databases, issue trackers, specialized debuggers).

MCP integration is structured as a progressive capability:
- In Phase 1–10, the core agent runtime, security sandbox, and native tools are solidified.
- In Phase 11, the MCP client layer connects external servers into the existing `ToolRegistry`.

---

## 2. Security Boundaries for MCP

External MCP tools cannot bypass CodeMind CLI's security architecture:
1. **Explicit Server Registration:** Servers must be explicitly declared in `.codemind/mcp.json` with command, environment, and user trust flags.
2. **Permission Inheritance:** Every tool exposed by an MCP server is mapped to an internal `PermissionLevel` (defaulting to requiring interactive approval for write/execute operations).
3. **Audit Trail:** Invocations and payloads of MCP tools are logged to the session event trace and redacted using the same secret shield.
