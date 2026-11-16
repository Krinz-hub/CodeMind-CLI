# CodeMind Phase 7 — Multi-Agent Collaboration and Sidecar Runtime
## Implementation Report & Technical Specification

**Author:** Principal AI Systems Architect & Senior Software Engineer  
**Date:** November 16, 2026  
**Status:** Completed & Validated  
**Target Model:** `qwen3.6:35b` (via local Ollama endpoint `http://127.0.0.1:11434`)  
**Core Test Suite:** 91 Hermetic Offline Tests Passed (0.81s)

---

## 1. Executive Summary

Phase 7 transforms CodeMind from a single-agent task orchestrator into a **coordinated multi-agent software engineering system**. The architecture introduces a supreme `MultiAgentCoordinator` delegating modular tasks across a directed acyclic graph (DAG) to specialized worker agents (`ResearchWorker`, `CodingWorker`, `DebuggingWorker`, `TestingWorker`). 

To address physical host constraints (local GPU VRAM thrashing and filesystem race conditions), Phase 7 establishes two critical architectural guarantees:
1. **Physical Workspace Isolation**: Workers execute strictly within isolated filesystem clones (`.codemind/workspaces/<worker_id>/`), emitting structured unified diffs (`ChangeProposal`) for coordinator review rather than mutating the primary repository directly.
2. **Local Inference Concurrency Gate**: An asynchronous semaphore-bounded queue (`InferenceGate`, `max_concurrent=1` default) regulates LLM generation turns across concurrent workers, ensuring peak local performance without thrashing memory.

All multi-agent communication adheres strictly to the versioned **Inter-Agent Communication Protocol (IACP v1)**, enforcing coordinator mediation and rejecting unauthorized peer-to-peer delegation or privilege escalation.

---

## 2. Architecture & Component Decomposition

```
                           ┌────────────────────────┐
                           │      User Request      │
                           └───────────┬────────────┘
                                       │
                                       ▼
                     ┌───────────────────────────────────┐
                     │       MultiAgentCoordinator       │
                     │  - Project Discovery & Memory     │
                     │  - Task Decomposition & Role DAG  │
                     │  - Conflict Detection & Merge     │
                     │  - Central Verification Runner    │
                     └─────────┬───────────────▲─────────┘
                               │               │
       ┌───────────────────────┼───────────────┼────────────────────────┐
       │ IACP v1 Protocol      │ (Task Assign) │ (Proposals & Findings) │
       ▼                       ▼               │                        │
┌──────────────────────────────────────────────────────────────────┐    │
│                        SidecarRuntime                            │    │
│  ┌───────────────────────┐          ┌──────────────────────────┐ │    │
│  │     MessageRouter     │          │      InferenceGate       │ │    │
│  │ (Mediation Invariants)│          │ (Bounded Concurrency = 1)│ │    │
│  └───────────────────────┘          └──────────────────────────┘ │    │
└──────────────┬───────────────────────────────┬───────────────────┘    │
               │                               │                        │
               ▼                               ▼                        │
     ┌──────────────────┐            ┌──────────────────┐               │
     │  ResearchWorker  │            │   CodingWorker   │               │
     │  - READ_ONLY     │            │  - TRUSTED       │               │
     │  - Reconnaissance│            │  - Implementation│               │
     └─────────┬────────┘            └─────────┬────────┘               │
               │                               │                        │
               │ Findings                      │ ChangeProposal (Diffs) │
               └───────────────────────────────┴────────────────────────┘
```

The system is implemented across 8 focused modules within `src/codemind/multiagent/` and CLI extensions:

| Module | Responsibilities | Key Classes & Functions |
|---|---|---|
| `models.py` | Data models, role definitions, and IACP v1 message schemas. | `AgentRole`, `WorkerStatus`, `MessageType`, `InterAgentMessage`, `WorkerConfig`, `ChangeProposal`, `MultiAgentConfig` |
| `protocol.py` | Routing mediation and communication invariant enforcement. | `MessageRouter`, `ProtocolViolationError` |
| `workspace.py` | Isolated disk sandboxes, unified diff computation, conflict detection, and safe merging. | `WorkerWorkspaceManager` |
| `workers.py` | Specialized worker implementations with role-scoped system prompts and capabilities. | `WorkerAgent`, `ResearchWorker`, `CodingWorker`, `DebuggingWorker`, `TestingWorker` |
| `sidecar.py` | Asynchronous worker process lifecycle, task dispatching, and bounded inference concurrency. | `SidecarRuntime`, `InferenceGate` |
| `coordinator.py` | Supreme multi-agent workflow coordinator managing decomposition, delegation, conflict resolution, and central verification. | `MultiAgentCoordinator` |
| `agents_cli.py` | CLI commands for inspecting and managing worker agents. | `codemind agents list`, `status`, `config`, `inspect`, `stop`, `logs` |
| `sidecar_cli.py` | CLI commands for sidecar telemetry and service lifecycle. | `codemind sidecar status`, `start`, `stop`, `workers` |

---

## 3. Inter-Agent Communication Protocol (IACP v1)

Inter-agent communication is governed by structured Pydantic payloads with strict routing invariants:

### A. Message Schema (`InterAgentMessage`)
```python
class InterAgentMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: f"msg-{uuid.uuid4().hex[:8]}")
    task_id: str
    sender_agent: str
    recipient: str
    timestamp: str
    message_type: MessageType
    payload: dict[str, Any]
    correlation_id: str | None = None
```

### B. Message Types
- `TASK_ASSIGNMENT`: Coordinator delegates subtask with scoped memory and skill context.
- `TASK_ACCEPTED`: Worker acknowledges assignment.
- `PROGRESS_UPDATE`: Intermediate worker execution milestone.
- `FINDINGS`: Reconnaissance data emitted by `ResearchWorker`.
- `CHANGE_PROPOSAL`: File modifications and unified diffs emitted by `CodingWorker` or `DebuggingWorker`.
- `REVIEW_REQUEST`: Test suite authoring and execution evidence emitted by `TestingWorker`.
- `BLOCKED`: Worker signals unmet preconditions or dependency blocks.
- `FAILURE`: Worker runtime exception or execution error caught by sidecar.
- `TASK_COMPLETED`: Successful subtask conclusion.

### C. Invariants Enforced by `MessageRouter`
1. **Coordinator Mediation**: Any direct worker-to-worker message (e.g. `worker-coding-1` $\rightarrow$ `worker-testing-2`) bypasses coordinator oversight and is immediately rejected with a `ProtocolViolationError`.
2. **Delegation Authority**: Only the `coordinator` can issue `TASK_ASSIGNMENT`. If a worker attempts to issue `TASK_ASSIGNMENT`, it is rejected as an unauthorized delegation attempt.
3. **Audit Traceability**: Every routed message is recorded in an in-memory chronological ledger queried by `get_messages_for_task()` and `get_messages_for_worker()`.

---

## 4. Specialized Worker Roles & Permissions

Each worker agent operates under scoped constraints:

| Role | Permission Mode | Allowed Tools | Operational Objective |
|---|---|---|---|
| **Research** (`ResearchWorker`) | `READ_ONLY` | `read_file`, `list_directory`, `search_files`, `search_text` | Explore codebase, analyze dependencies, identify architecture, emit `FINDINGS`. Modifications forbidden. |
| **Coding** (`CodingWorker`) | `TRUSTED` (Sandbox) | `read_file`, `create_file`, `write_file`, `apply_patch`, `list_directory` | Implement features and create modules in isolated sandbox. Emits `ChangeProposal` with diffs. |
| **Debugging** (`DebuggingWorker`) | `TRUSTED` (Sandbox) | `read_file`, `write_file`, `apply_patch`, `run_command` | Analyze failure traces, isolate root causes, apply minimal targeted repairs in sandbox. |
| **Testing** (`TestingWorker`) | `TRUSTED` (Sandbox) | `read_file`, `create_file`, `write_file`, `run_command` | Author regression and unit test suites following AAA pattern, execute tests, emit `REVIEW_REQUEST`. |

---

## 5. Workspace Isolation & Safe Integration Protocol

Direct concurrent modification of the main workspace tree risks corrupted partial writes and race conditions. Phase 7 implements a 5-step containment lifecycle:

1. **Mirror Provisioning (`WorkerWorkspaceManager`)**:
   - Sidecar creates a sandbox copy at `.codemind/workspaces/<worker_id>/`.
   - Filters out `.git`, `.codemind`, and temporary cache directories.
   - Captures an initial snapshot of all relative file paths and hashes.
2. **Containment Enforcement**:
   - `WorkspaceSandbox` enforces path boundary containment inside `.codemind/workspaces/<worker_id>/`.
   - Path traversal attempts (e.g., `../../secret.env`) trigger `SecurityViolationError`.
3. **Change Proposal Extraction**:
   - When a worker finishes, `WorkerWorkspaceManager.extract_change_proposal()` scans the worker sandbox against the initial snapshot.
   - Discovers created and modified files and generates standard unified diffs (`difflib.unified_diff`).
4. **Collision Detection**:
   - `detect_conflicts(proposals)` inspects pending proposals.
   - If two workers mutated the same file concurrently, coordinator detects the overlap, flags a conflict, and marks tasks `BLOCKED`, preventing corrupted merges.
5. **Atomic Primary Merge & Central Verification**:
   - Approved non-conflicting proposals are copied to the primary integration workspace.
   - `VerificationRunner` runs the discovered test runner (e.g. `unittest`) across the primary integration root.
   - Produces a verified `HonestCompletionReport`.

---

## 6. Resource Governance: The InferenceGate

Local LLMs (e.g. `qwen3.6:35b` at 22.6 GB) cannot service simultaneous concurrent generation requests without severe GPU thrashing, context truncation, or OOM crashes.

The `InferenceGate` provides asynchronous concurrency regulation:
- Uses `asyncio.Semaphore(max_concurrent=1)` by default.
- Workers acquire the gate immediately before LLM generation and release it immediately upon response receipt.
- Non-inference operations (file I/O, diff generation, AST parsing, and test execution) proceed concurrently without blocking.
- Tracks `inferences_in_flight` and `total_inferences_serviced` telemetry.

---

## 7. Shared Memory and Role-Scoped Skill Distribution

1. **Layer A-D Memory Filtering**: The coordinator queries `SQLiteProjectMemory` via `MemoryRetriever`, injecting only relevant project identity, conventions, and architectural decisions into the `TASK_ASSIGNMENT` payload. Workers do not access the SQLite database directly.
2. **Role-Scoped Skill Injections**:
   - `ResearchWorker` $\rightarrow$ `codebase-understanding`
   - `CodingWorker` $\rightarrow$ `python-backend`, `react-frontend`, `api-development`, `database-engineering`
   - `DebuggingWorker` $\rightarrow$ `debugging`
   - `TestingWorker` $\rightarrow$ `testing`

---

## 8. CLI Management Interface

Phase 7 introduces two new CLI command groups integrated into `codemind`:

### A. Worker Management (`codemind agents`)
- `codemind agents list`: Display specialized worker roles, permissions, and tool access.
- `codemind agents status`: Display active runtime state, worker counts, and inference metrics.
- `codemind agents config`: View and adjust worker concurrency limits.
- `codemind agents inspect <id>`: Inspect individual worker state, sandbox path, and history.
- `codemind agents stop <id>`: Terminate a running worker agent.
- `codemind agents logs <id>`: View audit event stream for a worker.

### B. Sidecar Management (`codemind sidecar`)
- `codemind sidecar status`: Health check, active inferences, and serviced turn telemetry.
- `codemind sidecar start`: Initialize local sidecar service.
- `codemind sidecar stop`: Terminate sidecar service and running workers.
- `codemind sidecar workers`: Tabulate active and registered worker instances.
