# CodeMind CLI — Release Readiness Checklist (Phase E)

> **Target Release:** CodeMind CLI v0.1.0  
> **Release Target:** Local-first, developer-companion CLI  
> **Evaluation Outcome:** APPROVED FOR RELEASE  

---

## 1. Correctness & Protocol Verification Gates

- [x] **Honest Completion Invariants:**
  - `HonestCompletionReport.evaluate_status()` prioritizes `is_cancelled` -> `CANCELLED`.
  - Prioritizes `is_paused` -> `PAUSED`.
  - Prioritizes `not task_completed` -> `INCOMPLETE`.
  - Prioritizes `missing_files` -> `MISSING_FILES`.
  - Internal test suite passing never overrides uncompleted user deliverables.
- [x] **Task-Scoped Change Ledgers:**
  - `AgentState.files_created` and `files_modified` initialized empty per task.
  - Previous interactive session snapshots do not contaminate new task completion reports.
- [x] **Bounded Protocol Repairs:**
  - `MalformedAction` loopbacks consume dedicated `repair_attempts` sub-budget (max 3).
  - Primary execution turns are never decremented on model format repair turns.
  - Exceeding repair budget halts task with clean diagnostic message rather than turn exhaustion.

---

## 2. Model Gateway & Privacy Gates

- [x] **Local-Only Compliance:**
  - `ModelGateway` validates endpoints and strictly blocks unauthorized cloud domains (e.g. `api.openai.com`, `anthropic.com`).
  - Zero telemetry or network payloads egress to external analytics.
- [x] **Capability Profiles:**
  - Explicit capability matrix (`supports_json_schema`, `supports_tool_calling`, `supports_cancellation`, `is_local`).
- [x] **Automated Context Compaction:**
  - `ContextCompactor` preserves system instructions, user prompt, active plan, and recent turns while compacting old messages.
  - Available dynamically via `/compact` slash command in REPL.

---

## 3. Developer Experience & CLI Gates

- [x] **Interactive Terminal (prompt_toolkit):**
  - Persistent command history preserved in `.codemind/history`.
  - Slash command auto-completion and fuzzy matching for all 15 commands (`/help`, `/status`, `/doctor`, `/models`, `/memory`, `/skills`, `/agents`, `/task`, `/diff`, `/mcp`, `/permissions`, `/compact`, `/resume`, `/clear`, `/exit`).
  - Graceful degradation in non-TTY, pipe, or `--plain` environments.
- [x] **File Mentions (`@file`):**
  - Path canonicalization and workspace containment checks (`is_within_workspace`).
  - Secret file protection (`.env`, `id_rsa`) prevents leaking credentials.
  - Content capped at 10 KB / 200 lines per file.

---

## 4. Integrations & Security Gates

- [x] **Model Context Protocol (MCP):**
  - stdio transport with JSON-RPC 2.0 handshake (`initialize`, `tools/list`, `tools/call`).
  - Dynamic schema generation (`make_mcp_args_schema`).
  - Individual server crashes do not crash the agent runtime.
  - Configurable and manageable via `.codemind/mcp.json` and `/mcp` command.
- [x] **Git Workflows:**
  - `git_branch`: List, create (`git checkout -b`), and switch branches.
  - `git_commit`: Conventional commits, clean working tree rejection, and secret file staging blocks.
  - `git_log`: Bounded commit history inspection.
- [x] **Declarative Security Policies:**
  - Rule matching by tool, command prefix (e.g. auto-approve `pytest`, deny `rm -rf`), and path pattern.
  - Explicit decisions (`allow`, `ask`, `deny`).

---

## 5. Test Suite & Verification Signoff

- [x] **Hermetic Test Suite:** 160 / 160 tests passing in ~2.2 seconds.
- [x] **Zero Flaky Tests:** All tests run hermetically offline without live external model dependency.
- [x] **Documentation Updated:** Architecture, roadmap, status ledger, evaluation report, and known limitations completed.
