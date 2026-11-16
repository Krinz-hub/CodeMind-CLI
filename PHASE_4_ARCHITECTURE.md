# CodeMind Phase 4 — Persistent Project Memory System Architecture

**Document Version:** 1.0.0  
**Status:** Approved Architecture Specification  
**Author:** Principal AI Systems Architect & Senior Python Engineer  
**Date:** 2026-11-16  
**System Target:** CodeMind CLI (Local-First Engineering Companion)

---

## 1. Executive Summary & Objective

In Phases 1 through 3, CodeMind CLI established a model-independent agent runtime loop, local Ollama integration, tool sandboxing, verification reporting, and session persistence. However, across distinct user sessions, the agent starts each new interaction tabula rasa—requiring costly, repetitive file-tree exploration, re-reading manifests, and re-discovering project conventions.

**Phase 4 introduces the Persistent Project Memory System.** Its core objective is to endow CodeMind CLI with long-term, cross-session recall of essential project knowledge, architectural decisions, task histories, and project-specific guidelines—**without cloud dependencies, paid APIs, model fine-tuning, or bloated vector databases.**

---

## 2. Layered Memory Architecture

Memory is organized into four distinct, semantically partitioned tiers to prevent prompt clutter and maintain high signal-to-noise ratio:

```
+-----------------------------------------------------------------------+
|                       CodeMind Context Engine                         |
+-----------------------------------------------------------------------+
      |                       |                       |
      v                       v                       v
[Project Identity]   [Active Task / Plan]   [Selected Memory Injections]
                                                          |
                                                          v
+-----------------------------------------------------------------------+
|             Persistent Project Memory System (.codemind/memory)        |
+-----------------------------------------------------------------------+
|  Layer A: Project Memory (Stable identity, tech stack, architecture)   |
|  Layer B: Decision Memory (ADRs: choices, rationales, trade-offs)     |
|  Layer C: Task Memory (Completed work, bug fixes, pending tasks)       |
|  Layer D: User Instruction Memory (Style rules, project constraints)  |
+-----------------------------------------------------------------------+
|             SQLite Storage Engine with FTS5 Full-Text Index           |
+-----------------------------------------------------------------------+
```

### Layer A: Project Memory (Relatively Stable)
Stores high-level structural and operational knowledge about the codebase:
- **Project Purpose & Identity:** Core domain and objectives.
- **Technology Stack & Dependencies:** Primary languages, frameworks, runtime versions.
- **Directory Structure & Entry Points:** Key modules, routers, main executables.
- **Database & Data Models:** Schemas, ORM models, migrations.
- **API & Protocol Conventions:** REST/GraphQL patterns, response formats.
- **Build & Test Commands:** Verified commands to compile, lint, and run tests.
- **Coding Conventions:** Formatting, typing standards, naming conventions.

### Layer B: Decision Memory (Architectural Decision Records - ADRs)
Captures significant technical choices so the agent does not propose previously rejected alternatives or contradict established architectural patterns:
- **Decision Title & Context:** What problem was being solved.
- **Chosen Alternative & Rationale:** Why a particular technology, library, or pattern was selected.
- **Rejected Alternatives:** What was considered and why it was dismissed.
- **Trade-Offs & Consequences:** Known downsides or limitations accepted.
- **Metadata:** Timestamp, session source, author/agent provenance, current status (`accepted`, `deprecated`, `superseded`).

### Layer C: Task Memory (Operational History & Continuity)
Tracks what has been accomplished, what failed, and what remains pending across sessions:
- **Features Implemented:** Added capabilities and affected modules.
- **Bugs Diagnosed & Fixed:** Defect descriptions, root causes, and verification proof.
- **Files Modified:** Comprehensive inventory of affected files.
- **Test Executions:** Recorded test outcomes and coverage signals.
- **Pending & Unresolved Work:** Known issues, technical debt, unfinished plan items.

### Layer D: User Instruction Memory (Project-Specific Directives)
Captures explicit user preferences and constraints specific to the workspace:
- **Preferred Coding Style:** e.g., "Use dataclasses rather than Pydantic in core models", "Prefer pure functions".
- **Framework & Library Rules:** e.g., "Use pytest instead of unittest", "Do not add third-party dependencies".
- **Architecture Constraints:** e.g., "Keep database logic in repositories, never in services".
- *Constraint Guard:* Temporary, task-specific instructions (e.g., "Fix line 12") are explicitly filtered out; only project-scoped preferences are retained.

---

## 3. Storage Design & Data Models

### 3.1 Local-First SQLite Engine
Rather than introducing heavy vector databases (Chroma, Qdrant, Milvus) that incur massive dependency footprints, require background daemon processes, or demand embedding models, CodeMind utilizes **SQLite 3 with FTS5** built directly into Python:
- **File Location:** `<workspace_root>/.codemind/memory/project_memory.db`
- **ACID & Interrupted Write Safety:** Standard WAL (Write-Ahead Logging) mode ensures atomic writes; interrupted processes or sudden crashes never corrupt the memory state.
- **Zero Cloud Footprint:** 100% offline, local-first, zero egress.
- **Project Isolation:** Physical separation per repository directory prevents any cross-project memory leakage.

### 3.2 Relational & FTS Schema Design

```sql
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Core memory records table
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

-- Full-Text Search (FTS5) index for lexical/BM25 retrieval
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    id UNINDEXED,
    title,
    content,
    category,
    content='memory_entries',
    content_rowid='rowid'
);

-- Triggers to maintain FTS index synchronized with memory_entries
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

## 4. Retrieval & Context Budgeting Engine

### 4.1 Token Budget Allocation
Memory injection must be disciplined. Injecting an entire database destroys model attention and causes prompt truncation. The Context Engine allocates explicit character budgets:

| Context Element | Maximum Character Budget | Fallback Strategy |
| :--- | :---: | :--- |
| **System Instructions & Protocol** | ~4,000 chars | Static, never truncated |
| **Project Summary & Structure** | ~5,000 chars | File tree summarized to depth 2 |
| **Persistent Memory Injection** | **~6,000 chars (~1,500 tokens)** | Top-$k$ relevance sorted, prioritized |
| **Active Plan & Guidelines** | ~3,000 chars | In-progress tasks prioritized |
| **Tool Definitions** | ~6,000 chars | Schema compacted |
| **Conversation History & Work** | Remaining Budget | Sliding window |

### 4.2 Multi-Stage Retrieval Pipeline
1. **Always-On Baseline (Layer A & D):**
   - Project Identity, primary build/test command, and active user instructions are loaded automatically into every session.
2. **Dynamic Relevance Retrieval (Layer B & C):**
   - Query text from user task instruction is tokenized.
   - FTS5 BM25 match identifies candidate decision and task records.
   - Scores are adjusted by:
     $$\text{Score} = \text{BM25\_Rank} \times 0.6 + \text{Recency\_Decay} \times 0.2 + \text{Pinned\_Weight} \times 0.2$$
3. **Stale Memory & Conflict Detection:**
   - Files referenced in retrieved memory records are cross-checked against actual filesystem paths via `os.path.exists()` and modification timestamps.
   - If a referenced file no longer exists or has been substantially rewritten, the memory is flagged as `stale` and excluded or downgraded.
   - **Ground Truth Invariant:** *Filesystem reality and verified test output always override memory records.*

---

## 5. Automatic Memory Distillation

Memory creation must be selective. Storing every conversational message bloats storage with transient noise. CodeMind executes a post-task distillation routine:

```
[Agent Execution Loop Ends]
           |
           v
[HonestCompletionReport]
  * Were files created/modified?
  * Did test verification run and PASS?
           |
     +-----+-----+
     |           |
 (Verified)  (Unverified/Failed)
     |           |
     |           +--> Record Unresolved Issue / Limitation into Task Memory
     v
[Distillation Engine]
  1. Secret Shield: Filter all API keys, tokens, passwords, and private certs
  2. Extract Accomplishments: Record feature/fix in Task Memory
  3. Extract Architecture Changes: Update Project Memory if entry points changed
  4. Deduplicate / Update: Check existing records; update existing vs insert new
  5. Commit Transaction to SQLite
```

---

## 6. CLI Management Commands

Integrated seamlessly into `codemind memory`:

| Command | Purpose |
| :--- | :--- |
| `codemind memory status` | Displays total memories across layers, DB size, last update, and DB health. |
| `codemind memory show` | Renders a human-readable summary of project identity, decisions, and recent tasks. |
| `codemind memory search <query>` | Performs fast FTS5 full-text search across all memory layers. |
| `codemind memory list [--layer <type>]` | Lists all structured entries, filtered by layer (`project`, `decision`, `task`, `instruction`). |
| `codemind memory update <id>` | Manually edits, pins, or supersedes a specific memory record. |
| `codemind memory rebuild` | Re-scans repository structure and manifests, refreshing Project Memory from ground truth. |
| `codemind memory clear [--layer <type>]` | Safely purges memory entries (with confirmation prompt). |

---

## 7. Security, Privacy & Integrity Guarantees

1. **Untrusted Memory Model:** Memory is contextual prompt injection data. CodeMind treats memory as advisory, never executable. Memory contents can never directly invoke shell commands or grant permission bypasses.
2. **Secret Redaction Gate:** All memory entries pass through `redact_secrets()` prior to persistence. API keys, JWTs, private keys, and environment variables are strictly prevented from entering the SQLite store.
3. **Strict Project Isolation:** SQLite databases reside strictly within `<workspace_root>/.codemind/memory/`. CodeMind never queries or links across different workspace roots.
4. **Crash & Power-Failure Resilience:** SQLite ACID transactions guarantee that partial writes or aborted sessions leave the database in a clean, consistent state.

---

## 8. Phase 4 Evaluation Plan (`benchmarks/phase_4/`)

Ten exhaustive scenarios will be executed and recorded:
- **Scenario A:** Architecture recall in a brand-new session without exploration.
- **Scenario B:** Architectural Decision recall (e.g., choice of library) across sessions.
- **Scenario C:** Unresolved task recall from a previous interrupted session.
- **Scenario D:** Selective retrieval relevance (unrelated task does not load irrelevant records).
- **Scenario E:** Stale memory detection after file deletion/modification.
- **Scenario F:** Conflict resolution between superseded and active decisions.
- **Scenario G:** Strict project isolation (no cross-contamination between Project 1 and Project 2).
- **Scenario H:** Secret shield enforcement (rejecting API keys from memory).
- **Scenario I:** Memory rebuild verification after structural codebase changes.
- **Scenario J:** Crash/interrupted write recovery without corruption.

---

## 9. Verification & Approval Checklist

- [x] Repository audit completed; no competing context systems introduced.
- [x] Zero cloud or vector DB dependencies required.
- [x] Strict backward compatibility with Phase 1–3 offline tests (46/46 tests must pass).
- [x] Clean separation between transient session state and permanent project memory.
