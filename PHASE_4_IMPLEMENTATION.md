# CodeMind Phase 4 — Persistent Project Memory Implementation Report

**Document Version:** 1.0.0  
**Status:** Completed & Integrated  
**Author:** Principal AI Systems Architect & Senior Python Engineer  
**Date:** 2026-11-16  
**System Target:** CodeMind CLI

---

## 1. Executive Summary

Phase 4 of CodeMind CLI introduces a **local-first, persistent project memory system** designed to solve cross-session amnesia. Prior to Phase 4, the agent approached every new session tabula rasa, repeatedly performing expensive repository scans, file tree listings, and manifest parsing. 

With Phase 4, CodeMind remembers:
- Stable project identity, tech stacks, and verified test commands (Layer A).
- Architectural Decision Records (ADRs) with rationale and rejected alternatives (Layer B).
- Operational history, including completed features, bug fixes, and unresolved technical debt (Layer C).
- Workspace guidelines and user coding directives (Layer D).

The entire system is implemented using **SQLite 3 with FTS5 full-text indexing**, requiring **zero cloud dependencies, zero external vector databases, zero paid APIs, and zero model fine-tuning**.

---

## 2. Layered Memory Architecture

```
+-------------------------------------------------------------------------+
|                         CodeMind Context Engine                         |
+-------------------------------------------------------------------------+
       |                                    |                        |
       v                                    v                        v
[System Protocol]                 [Project Context]          [Active Plan]
       |                                                             |
       +----------------------------+--------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|         --- PERSISTENT PROJECT MEMORY --- (Budget: ~6,000 chars)        |
+-------------------------------------------------------------------------+
| ▶ Layer D: Workspace Guidelines & Directives (Pinned style rules)      |
| ▶ Layer A: Persistent Project Knowledge (Identity, stack, test cmd)    |
| ▶ Layer B: Relevant Architectural Decisions (BM25 retrieved ADRs)       |
| ▶ Layer C: Relevant Prior Tasks & Defect History (BM25 retrieved tasks) |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|      Local SQLite Storage Engine with FTS5 (.codemind/memory/)          |
+-------------------------------------------------------------------------+
```

### 2.1 The Four Memory Tiers

1. **Layer A — Project Memory (Relatively Stable):**
   - High-level project identity, purpose, technology stack, manifest inventory, directory layout, and verified build/test commands.
   - Pinned by default to guarantee the model immediately understands the repo without file exploration.

2. **Layer B — Decision Memory (Architectural Decision Records):**
   - Engineering decisions, rationale, rejected alternatives, trade-offs, and lifecycle status (`active`, `superseded`, `deprecated`).
   - Prevents the agent from re-proposing previously rejected patterns (e.g. using cookies when JWT was chosen).

3. **Layer C — Task Memory (Operational History & Continuity):**
   - Completed features, fixed bugs with verified test proof, modified files, and unresolved technical issues or debt.
   - Enables continuous multi-session engineering without losing track of pending tasks.

4. **Layer D — User Instruction Memory (Workspace Directives):**
   - Explicit project-level preferences (e.g. "Always use type hints", "Prefer dataclasses over Pydantic in core models").
   - Filtered through a directive pattern engine to ensure ephemeral prompt instructions (e.g., "Fix line 10") are never mistakenly stored as permanent rules.

---

## 3. Storage Engine & Schema Specification

### 3.1 SQLite 3 with FTS5 Full-Text Search
- **Path:** `<workspace_root>/.codemind/memory/project_memory.db`
- **ACID Safety:** Write-Ahead Logging (`PRAGMA journal_mode=WAL;`) with `PRAGMA synchronous=NORMAL;` prevents corruption even during sudden crashes or power loss.
- **Physical Project Isolation:** Each workspace maintains its own isolated database file; memories never leak across different repositories.

### 3.2 Schema Definition

```sql
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Core memory entries
CREATE TABLE IF NOT EXISTS memory_entries (
    id TEXT PRIMARY KEY,
    layer TEXT NOT NULL CHECK(layer IN ('project', 'decision', 'task', 'instruction')),
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'superseded', 'deprecated')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    pinned INTEGER NOT NULL DEFAULT 0
);

-- External content FTS5 index
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    id UNINDEXED,
    title,
    content,
    category,
    content='memory_entries',
    content_rowid='rowid'
);

-- Automatic FTS synchronization triggers
CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory_entries BEGIN
    INSERT INTO memory_fts(rowid, id, title, content, category)
    VALUES (new.rowid, new.id, new.title, new.content, new.category);
END;

CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory_entries BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, id, title, content, category)
    VALUES('delete', old.rowid, old.id, old.title, old.content, old.category);
END;

CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memory_entries BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, id, title, content, category)
    VALUES('delete', old.rowid, old.id, old.title, old.content, old.category);
    INSERT INTO memory_fts(rowid, id, title, content, category)
    VALUES (new.rowid, new.id, new.title, new.content, new.category);
END;
```

---

## 4. Key Subsystems Implemented

### 4.1 Models (`src/codemind/memory/models.py`)
- `MemoryLayer`: `PROJECT`, `DECISION`, `TASK`, `INSTRUCTION`.
- `MemoryStatus`: `ACTIVE`, `SUPERSEDED`, `DEPRECATED`.
- `MemoryEntry`: Pydantic model with strict validation, metadata serializing, and provenance tracking.
- `MemorySearchResult`: Wraps search hits with BM25 score, match reason, and staleness flag.
- `MemoryStats`: Metrics model for DB size, entry counts, and schema versions.

### 4.2 Storage Engine (`src/codemind/memory/store.py`)
- Class `SQLiteProjectMemory`:
  - `add_entry(entry)`: Scans for secrets, scrubs credentials, and writes atomically.
  - `get_entry(id)` / `update_entry(...)` / `delete_entry(id)`: Full CRUD lifecycle.
  - `list_entries(layer, status, limit)`: Filtered listing.
  - `search(query, layer, status, limit)`: FTS5 BM25 search with fallback to LIKE query on complex punctuation.
  - `check_stale(entry)`: Inspects referenced file paths against actual disk paths, flagging missing files.
  - `rebuild_from_project(project_summary)`: Dynamic ground-truth re-sync.
  - `clear(layer)`: Selective or total memory purge.
  - Backward compatibility: Preserves `set_fact()`, `get_fact()`, and `list_facts()`.

### 4.3 Multi-Stage Retrieval Engine (`src/codemind/memory/retriever.py`)
- Class `MemoryRetriever`:
  - Always injects Layer D (User Directives) and Layer A (Project Identity & Test Command).
  - Performs BM25 relevance matching for Layer B (ADRs) and Layer C (Tasks) based on the user's task instruction.
  - Flags or suppresses stale memories and superseded decisions.
  - Enforces a strict token/character budget (~6,000 characters) to prevent prompt bloat.

### 4.4 Automatic Memory Distillation (`src/codemind/memory/distiller.py`)
- Class `MemoryDistiller`:
  - Executes automatically at the end of `CodeMindAgent.run_task`.
  - Distills verified tasks into Layer C with verification proof (`report.verified == True`).
  - Distills unverified or failed tasks into Layer C as unresolved technical debt.
  - Detects persistent workspace directives from prompt text and logs them into Layer D.
  - Normalizes all file paths to workspace-relative paths for maximum portability.
  - Passes all text through the Secret Shield gate prior to storage.

### 4.5 CLI Management Suite (`src/codemind/cli/memory_cli.py`)
Registered under `codemind memory`:
- `codemind memory status`: Database file path, schema version, total entries, layer counts, and file size.
- `codemind memory show`: Human-readable summary of active project memory across all layers.
- `codemind memory search <query>`: Fast FTS5 search with BM25 scores and staleness indicators.
- `codemind memory list [--layer <layer>] [--status <status>]`: Tabular entry listing.
- `codemind memory update <id>`: Modify content, change status (`active`/`superseded`), pin/unpin.
- `codemind memory rebuild`: Re-scans repository structure and refreshes baseline Layer A records.
- `codemind memory clear [--layer <layer>] [--force]`: Purges memory records safely.

---

## 5. Security & Privacy Guarantees

1. **Untrusted Memory Model:** Memory entries are purely informational prompt context. The agent never executes memory content directly as shell scripts or code.
2. **Secret Shield Gate:** Every entry passing through `add_entry`, `update_entry`, or `distiller.distill` is sanitized using `redact_secrets()`. OpenAI keys (`sk-...`), GitHub PATs (`ghp_...`), AWS credentials (`AKIA...`), and Bearer tokens are scrubbed to `[REDACTED_...]` placeholders in both SQLite tables and FTS5 indices.
3. **Physical Project Boundary:** Memory resides strictly inside `.codemind/memory/` within the target project root. No cross-project leaking or global memory pollution can occur.

---

## 6. Test Suite & Verification Results

All 57 automated offline tests pass hermetically in under 0.4 seconds:

```
============================================================
▟●▙ CodeMind CLI - Hermetic Offline Test Suite
============================================================
test_full_loop_workflow (integration.test_agent_loop.TestAgentLoopIntegration.test_full_loop_workflow) ... ok
test_cross_session_memory_recall (integration.test_memory_integration.TestMemoryIntegration.test_cross_session_memory_recall) ... ok
test_run_check_and_generate_report (integration.test_verification.TestVerificationIntegration.test_run_check_and_generate_report) ... ok
test_blocks_reading_dot_env (security.test_secret_shield.TestSecretShield.test_blocks_reading_dot_env) ... ok
test_blocks_reading_pem_files (security.test_secret_shield.TestSecretShield.test_blocks_reading_pem_files) ... ok
test_apply_patch_blocks_traversal (security.test_traversal_prevention.TestTraversalPrevention.test_apply_patch_blocks_traversal) ... ok
test_create_file_blocks_traversal (security.test_traversal_prevention.TestTraversalPrevention.test_create_file_blocks_traversal) ... ok
test_read_file_blocks_traversal (security.test_traversal_prevention.TestTraversalPrevention.test_read_file_blocks_traversal) ... ok
test_help_flag (unit.test_cli.TestCLI.test_help_flag) ... ok
test_memory_cli_commands (unit.test_cli.TestCLI.test_memory_cli_commands) ... ok
test_status_command (unit.test_cli.TestCLI.test_status_command) ... ok
test_version_flag (unit.test_cli.TestCLI.test_version_flag) ... ok
test_default_config (unit.test_config.TestConfig.test_default_config) ... ok
test_env_var_overrides (unit.test_config.TestConfig.test_env_var_overrides) ... ok
test_json_config_file (unit.test_config.TestConfig.test_json_config_file) ... ok
test_context_budget_assembly (unit.test_context.TestContext.test_context_budget_assembly) ... ok
test_ignore_engine (unit.test_context.TestContext.test_ignore_engine) ... ok
test_project_discovery (unit.test_context.TestContext.test_project_discovery) ... ok
test_evaluator_with_mock_model (unit.test_evaluator.TestEvaluator.test_evaluator_with_mock_model) ... ok
test_cross_project_isolation (unit.test_memory.TestProjectMemory.test_cross_project_isolation) ... ok
test_crud_operations (unit.test_memory.TestProjectMemory.test_crud_operations) ... ok
test_fts5_bm25_search_and_ranking (unit.test_memory.TestProjectMemory.test_fts5_bm25_search_and_ranking) ... ok
test_legacy_backward_compatibility (unit.test_memory.TestProjectMemory.test_legacy_backward_compatibility) ... ok
test_memory_distiller (unit.test_memory.TestProjectMemory.test_memory_distiller) ... ok
test_memory_retriever_context_budget (unit.test_memory.TestProjectMemory.test_memory_retriever_context_budget) ... ok
test_secret_redaction_gate (unit.test_memory.TestProjectMemory.test_secret_redaction_gate) ... ok
test_sqlite_memory_init_and_schema (unit.test_memory.TestProjectMemory.test_sqlite_memory_init_and_schema) ... ok
test_stale_memory_detection (unit.test_memory.TestProjectMemory.test_stale_memory_detection) ... ok
test_discovery_with_mock_models (unit.test_model_discovery.TestModelDiscovery.test_discovery_with_mock_models) ... ok
test_create_adapter_factory (unit.test_models.TestModels.test_create_adapter_factory) ... ok
test_mock_adapter_generation (unit.test_models.TestModels.test_mock_adapter_generation) ... ok
test_mock_adapter_health (unit.test_models.TestModels.test_mock_adapter_health) ... ok
test_models_current_command (unit.test_models_cli.TestModelsCLI.test_models_current_command) ... ok
test_models_list_command (unit.test_models_cli.TestModelsCLI.test_models_list_command) ... ok
test_models_use_command (unit.test_models_cli.TestModelsCLI.test_models_use_command) ... ok
test_plan_lifecycle (unit.test_planner.TestPlanner.test_plan_lifecycle) ... ok
test_update_from_model_action (unit.test_planner.TestPlanner.test_update_from_model_action) ... ok
test_invalid_type (unit.test_protocol.TestProtocol.test_invalid_type) ... ok
test_parse_fenced_json (unit.test_protocol.TestProtocol.test_parse_fenced_json) ... ok
test_parse_final_action (unit.test_protocol.TestProtocol.test_parse_final_action) ... ok
test_parse_malformed_non_json (unit.test_protocol.TestProtocol.test_parse_malformed_non_json) ... ok
test_parse_tool_call (unit.test_protocol.TestProtocol.test_parse_tool_call) ... ok
test_unsupported_protocol_version (unit.test_protocol.TestProtocol.test_unsupported_protocol_version) ... ok
test_leave_clean_text_intact (unit.test_redaction.TestRedaction.test_leave_clean_text_intact) ... ok
test_redact_bearer_header (unit.test_redaction.TestRedaction.test_redact_bearer_header) ... ok
test_redact_github_token (unit.test_redaction.TestRedaction.test_redact_github_token) ... ok
test_redact_openai_key (unit.test_redaction.TestRedaction.test_redact_openai_key) ... ok
test_canonicalize_and_containment (unit.test_sandbox.TestSandbox.test_canonicalize_and_containment) ... ok
test_path_traversal_detection (unit.test_sandbox.TestSandbox.test_path_traversal_detection) ... ok
test_secret_file_blocking (unit.test_sandbox.TestSandbox.test_secret_file_blocking) ... ok
test_symlink_escape_blocking (unit.test_sandbox.TestSandbox.test_symlink_escape_blocking) ... ok
test_append_event_trace (unit.test_sessions.TestSessions.test_append_event_trace) ... ok
test_save_and_load_session (unit.test_sessions.TestSessions.test_save_and_load_session) ... ok
test_apply_patch_tool (unit.test_tools.TestTools.test_apply_patch_tool) ... ok
test_create_and_read_file (unit.test_tools.TestTools.test_create_and_read_file) ... ok
test_run_command_tool (unit.test_tools.TestTools.test_run_command_tool) ... ok
test_search_files_and_text (unit.test_tools.TestTools.test_search_files_and_text) ... ok

----------------------------------------------------------------------
Ran 57 tests in 0.362s

OK
============================================================
✓ All 57 tests passed successfully!
============================================================
```
