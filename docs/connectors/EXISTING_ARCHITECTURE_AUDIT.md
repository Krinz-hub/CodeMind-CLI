# CodeMind CLI — Existing Architecture Audit for Universal App Connector Marketplace

> **Audit Date:** November 16, 2026  
> **Author:** Principal Software Architect  
> **Target System:** CodeMind CLI v0.1.0  
> **Audit Purpose:** Establish architectural baseline and integration points for the Universal Application Connector Ecosystem (YouTube, Gmail, Google Drive, Google Calendar, Discord, Slack, Notion, Spotify, and MCP).

---

## 1. Executive Summary

CodeMind CLI is a local-first autonomous AI engineering companion built in Python 3.10+ on Apple Silicon and POSIX systems. Prior to introducing external application connectors, the platform underwent an extensive reliability remediation across five engineering phases (Phases A through E), reaching **160 hermetic tests passing with a 100% pass rate in ~2.1 seconds**.

The core system is strictly local: it communicates with local inference engines (Ollama, local endpoints, or mock adapters), enforces workspace filesystem containment via a sandboxed virtual root, manages fine-grained permissions, and isolates tool executions through an auditable registry.

This audit details each existing component, evaluates reusable primitives, inspects existing MCP infrastructure, identifies security boundaries, and maps the exact extension points required to host external application connectors safely.

---

## 2. Component-by-Component Architecture Mapping

```
                                  ┌───────────────────────────┐
                                  │      CodeMind CLI REPL    │
                                  │  (Typer, prompt_toolkit)  │
                                  └─────────────┬─────────────┘
                                                │
                                                ▼
                                  ┌───────────────────────────┐
                                  │       CodeMindAgent       │
                                  │   (Runtime Orchestrator)  │
                                  └─────────────┬─────────────┘
                                                │
                 ┌──────────────────────────────┼──────────────────────────────┐
                 │                              │                              │
                 ▼                              ▼                              ▼
   ┌───────────────────────────┐  ┌───────────────────────────┐  ┌───────────────────────────┐
   │       ModelGateway        │  │       ToolRegistry        │  │     Security & Policy     │
   │  - Local-Only Policy      │  │  - BaseTool Execution     │  │  - PermissionChecker      │
   │  - Capability Profiles    │  │  - Interactive Approvals  │  │  - WorkspaceSandbox       │
   │  - Streaming Accumulation │  │  - Schema Validation      │  │  - Secret Redaction       │
   └───────────────────────────┘  └─────────────┬─────────────┘  └───────────────────────────┘
                                                │
                        ┌───────────────────────┴───────────────────────┐
                        │                                               │
                        ▼                                               ▼
         ┌─────────────────────────────┐                 ┌─────────────────────────────┐
         │     Built-in Local Tools    │                 │      MCP Infrastructure     │
         │ (Filesystem, Git, Terminal) │                 │  (stdio JSON-RPC Client)    │
         └─────────────────────────────┘                 └─────────────────────────────┘
```

### 2.1 Agent Runtime & Execution Loop
- **`CodeMindAgent` ([`src/codemind/runtime/agent.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/runtime/agent.py)):**
  - High-level coordinator holding single instances of `ModelAdapter`, `ToolRegistry`, `PermissionChecker`, `WorkspaceSandbox`, `ProjectDiscovery`, `SessionManager`, `SQLiteProjectMemory`, `SkillRegistry`, `VerificationRunner`, and `MCPManager`.
  - Initializes sessions via `initialize(resume_session_id=...)` and executes tasks via `run_task(instruction=...)`.
  - Dispatches tasks to `AgentLoop` with a fresh task-scoped file change ledger, guaranteeing zero session contamination.
- **`AgentLoop` ([`src/codemind/runtime/loop.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/runtime/loop.py)):**
  - Manages the turn-by-turn iterative loop up to `config.runtime.max_turns` (default 20).
  - Handles protocol parsing via `ProtocolParser.parse()`, discriminating between `ToolCallAction`, `PlanAction`, and `FinalResponseAction`.
  - Enforces turn budgeting: format errors (`MalformedAction`) consume a dedicated 3-attempt repair sub-budget, never decrementing primary execution turns.
  - Automatically compacts conversation context via `ContextCompactor` when messages exceed token budget limits.
- **`AgentState` ([`src/codemind/runtime/state.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/runtime/state.py)):**
  - Maintains conversation messages (`ChatMessage`), active task plan (`TaskPlan`), files created/modified, and pause/cancellation flags.

### 2.2 Tool System & Invocation Pipeline
- **`BaseTool` ([`src/codemind/tools/base.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/tools/base.py)):**
  - Abstract base class requiring:
    - `name: str`: Tool identifier.
    - `description: str`: Natural language capability description exposed to the model.
    - `permission_level: PermissionLevel`: Risk classification (`READ_ONLY`, `READ_WRITE`, `EXECUTE`, `DANGEROUS`).
    - `args_schema: type[BaseModel]`: Pydantic model defining arguments and JSON schema.
    - `async def execute(arguments: dict[str, Any], context: ExecutionContext) -> ToolResult`.
- **`ExecutionContext` ([`src/codemind/tools/base.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/tools/base.py)):**
  - Provides `workspace_root: Path`, `sandbox: WorkspaceSandbox`, `permission_checker: PermissionChecker`, `max_output_bytes: int` (64 KB limit), and `truncate_output()`.
- **`ToolRegistry` ([`src/codemind/tools/registry.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/tools/registry.py)):**
  - Central repository holding registered tools.
  - `execute(tool_name, arguments, context)` strictly gates execution:
    1. Evaluates permissions via `context.permission_checker.evaluate()`.
    2. Enforces interactive human approval gate (`context.ui.request_approval`) if `decision.requires_approval` is `True`.
    3. Validates incoming arguments against `tool.args_schema.model_validate(arguments)`.
    4. Awaits tool execution and redacts secrets from error messages.

### 2.3 Model Gateway & Local Policy
- **`ModelGateway` ([`src/codemind/models/gateway.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/models/gateway.py)):**
  - Unified inference facade enforcing a strict **local-only policy**: rejects cloud endpoints (`api.openai.com`, `anthropic.com`) to prevent accidental data exfiltration.
  - Exposes `ModelCapabilityProfile` tracking JSON schema support, tool calling support, and context limits.
- **Adapters ([`src/codemind/models/`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/models/)):**
  - `OllamaAdapter`: Connects to local Ollama server (e.g., `http://127.0.0.1:11434`).
  - `MockModelAdapter`: Deterministic, offline canned response generator used in hermetic tests.
  - `CustomModelAdapter`: OpenAI-compatible local endpoints (vLLM, LM Studio, LocalAI).
  - `CodeMindLocalAdapter`: Built-in local runtime adapter.

### 2.4 Security, Sandboxing & Permission Management
- **`PermissionChecker` ([`src/codemind/security/permissions.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/security/permissions.py)):**
  - Evaluates tool operations across three base modes:
    - `READ_ONLY`: Rejects write, execute, or dangerous tools.
    - `SUPERVISED`: Read-only actions auto-allowed; write/execute/dangerous actions require interactive approval.
    - `TRUSTED`: Safe internal workspace reads/writes auto-allowed; shell execution and dangerous tools require approval.
- **`PermissionPolicyEngine` ([`src/codemind/security/permissions.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/security/permissions.py)):**
  - Declarative policy rules loaded from `.codemind/permissions.yaml` or `.codemind/permissions.json`.
  - Matches rules by `tool`, `command_prefix` (e.g. auto-approve `pytest`, block `rm -rf`), or `path_pattern` (`*.secret`).
  - Explicit rule decisions: `ALLOW`, `ASK`, `DENY`.
- **`WorkspaceSandbox` ([`src/codemind/security/sandbox.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/security/sandbox.py)):**
  - Enforces workspace containment (`is_within_workspace`).
  - Blocks path traversal (`../`), symlink escapes, and secret files (`.env`, `id_rsa`, `id_ed25519`).
- **`redact_secrets` ([`src/codemind/security/redaction.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/security/redaction.py)):**
  - Regex scrubber for Bearer tokens, API keys, passwords, OpenAI keys, GitHub tokens, AWS keys, and private key blocks.

### 2.5 Storage, Memory & Session Management
- **`SessionManager` ([`src/codemind/sessions/manager.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/sessions/manager.py)):**
  - Manages session directories under `.codemind/sessions/<session_id>/`.
  - Appends audit events to `<session_id>.events.jsonl` with timestamps and exit codes.
- **`SQLiteProjectMemory` ([`src/codemind/memory/store.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/memory/store.py)):**
  - ACID-compliant SQLite store at `.codemind/memory/project_memory.db`.
  - Stores project facts, architecture layers, and distilled insights with FTS search capabilities.
- **`CheckpointManager` ([`src/codemind/orchestration/checkpoint.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/orchestration/checkpoint.py)):**
  - Serializes task checkpoints to `.codemind/checkpoints/<session_id>_<task_id>.json` for recovery.

### 2.6 CLI, REPL & User Interface
- **`main.py` ([`src/codemind/cli/main.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/cli/main.py)):**
  - Typer CLI entry points: `codemind run`, `codemind resume`, `codemind doctor`, `codemind status`, `codemind memory`, `codemind task`, `codemind agents`.
  - Interactive companion REPL via `run_interactive()`.
- **`repl.py` ([`src/codemind/cli/repl.py`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/cli/repl.py)):**
  - Built with `prompt_toolkit`.
  - Provides persistent command history (`.codemind/history`), slash command auto-completion, and dynamic `@file` fuzzy completions.
  - Slash command handler `handle_slash_command`: supports `/help`, `/status`, `/doctor`, `/models`, `/memory`, `/skills`, `/agents`, `/task`, `/diff`, `/mcp`, `/permissions`, `/compact`, `/resume`, `/clear`, `/exit`.

### 2.7 Existing MCP Implementation (Phase D Deliverable)
- **`src/codemind/mcp/`:**
  - `client.py`: `MCPClient` implementing stdio JSON-RPC 2.0 (`initialize` handshake, `notifications/initialized`, `tools/list`, `tools/call`).
  - `models.py`: `MCPServerConfig`, `MCPToolDefinition`, `MCPServersConfig`.
  - `tool.py`: `MCPProxyTool` wrapping external tools into `BaseTool`, with dynamic schema generation via `make_mcp_args_schema()`.
  - `manager.py`: `MCPManager` reading `.codemind/mcp.json`, auto-discovering tools upon agent initialization, and handling server additions/disabling.

---

## 3. Reusable Assets & Identified Gaps for Connectors

| Capability Needed | Existing CodeMind Primitive | Gap to Bridge for Connectors |
|---|---|---|
| **Tool Execution & Safety** | `BaseTool`, `ToolRegistry`, `ExecutionContext` | Connectors can inherit from `BaseTool` or bridge via `ConnectorAdapter` into `ToolRegistry`. |
| **Interactive Approvals** | `PermissionChecker`, `ui.request_approval()` | SENSITIVE connector actions (send email, delete file, upload video) must hook into this gate. |
| **Secret Redaction** | `redact_secrets()` in `src/codemind/security/redaction.py` | Must be applied to OAuth access tokens, refresh tokens, and webhook URLs. |
| **Declarative Permissions** | `PermissionPolicyEngine`, `.codemind/permissions.yaml` | Add connector-scoped policy rules (e.g., `connector: gmail`, `action: send_email`, `decision: ask`). |
| **Audit Logging** | `SessionManager.append_event()` (`.events.jsonl`) | Connector operations must log structured audit entries without exposing credential tokens. |
| **Local SQLite Storage** | `SQLiteProjectMemory` pattern (`src/codemind/memory/store.py`) | Reusable pattern for `CredentialVault` (storing encrypted tokens, expiry, and scopes). |
| **Async HTTP Client** | `httpx>=0.24.0` in `pyproject.toml` | Full async support for OAuth token exchanges, REST API requests, and SSE streams. |
| **CLI Management** | Typer subcommands & REPL slash commands | Add `codemind connectors` command group and `/connectors` REPL command. |

---

## 4. Key Architectural Constraints & Invariants

1. **Local-First Security:**
   - Under no circumstances will user OAuth refresh tokens or credentials be committed to git or stored in plain project files.
   - Credentials must be stored in an encrypted local vault (or OS keychain).
2. **Untrusted External Data:**
   - Content returned by external APIs (emails, discord messages, notion pages) must be treated as untrusted user data, never concatenated directly into system instructions without boundary markers.
3. **No False-Success:**
   - An action (e.g. sending an email or publishing a video) must verify the provider's authoritative API response code and ID. Mock tests must be explicitly labeled and separated from real connectivity tests.
4. **Resilient Failure Isolation:**
   - Unreachable connectors or expired OAuth tokens must gracefully return informative error cards to the agent rather than crashing the execution loop.

---

## 5. Audit Conclusion

CodeMind's architecture is fully prepared to host the **Universal App Connector Marketplace**. The foundation of `BaseTool`, `ToolRegistry`, `PermissionChecker`, `ExecutionContext`, and `MCPManager` provides the exact abstraction layers required.

The next step is to design and implement the **Connector Architecture** (`ConnectorRegistry`, `ConnectorManager`, `ConnectorAdapter`, `ConnectorAuthManager`, `OAuthManager`, `CredentialVault`, `ConnectorPermissionManager`, `ConnectorHealthMonitor`, and `ConnectorAuditLogger`).
