# CodeMind Phase 7 — Multi-Agent Collaboration and Sidecar Runtime: Architecture Specification

## 1. Executive Summary & Design Principles

Phase 7 evolves CodeMind from a single-agent orchestrator into a coordinated, multi-agent software engineering system. Complex software development workflows—such as full-stack feature delivery, refactoring, comprehensive test generation, and deep debugging—benefit significantly from role specialization, isolated execution sandboxes, and independent verification.

### Core Architectural Invariants:
1. **Local-First & Model-Independent**: Operates locally with `qwen3.6:35b` via Ollama without requiring paid cloud APIs, model downloads, or fine-tuning.
2. **Coordinator Supremacy**: The `MultiAgentCoordinator` is the sole authority for task delegation, inter-agent message routing, integration merging, and overall task completion. Worker agents cannot declare the overall user task complete or instruct peers directly.
3. **Workspace Isolation & Safe Integration**: Coding workers execute within isolated workspace sandboxes (e.g., `<workspace>/.codemind/workspaces/<worker_id>/`). No worker writes directly to the live integration tree without coordinator conflict inspection and approval.
4. **Local Asynchronous Sidecar**: The sidecar runtime coordinates worker lifecycles, IPC, and event streams through Python-native asynchronous channels (`asyncio.Queue` / local event dispatch). Unauthenticated network ports, Kafka, Redis, or Kubernetes are strictly forbidden.
5. **Inference Concurrency Bounding**: Recognizes local GPU and unified-memory constraints. Shared inference semaphores prevent local LLM resource exhaustion while allowing non-inference tasks (AST parsing, test runs, diff computation) to proceed concurrently.

---

## 2. Multi-Agent System Topology

```
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     User / CLI Interface                                       │
│          codemind "build feature X"   │   codemind agents list   │   codemind sidecar status   │
└───────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                │
┌───────────────────────────────────────────────▼────────────────────────────────────────────────┐
│                                   MultiAgentCoordinator                                        │
│  - Understands project requirements           - Builds hierarchical task DAG                   │
│  - Selects & configures worker roles          - Mediates inter-agent message routing           │
│  - Resolves merge & dependency conflicts      - Enforces central verification & completion     │
└───────┬───────────────────────────────┬───────────────────────────────┬────────────────────────┘
        │                               │                               │
┌───────▼───────────────────────────────▼───────────────────────────────▼────────────────────────┐
│                                       SidecarRuntime                                           │
│  - Worker registration & lifecycle            - Structured IPC message broker (P2C / C2P)      │
│  - Bounded inference concurrency queue        - Progress auditing, health checks & termination │
└───────┬───────────────────────────────┬───────────────────────────────┬────────────────────────┘
        │                               │                               │                        │
┌───────▼──────────────┐┌───────────────▼──────┐┌───────────────▼──────┐┌────────────────▼───────┐
│    ResearchAgent     ││     CodingAgent      ││   DebuggingAgent     ││      TestingAgent      │
│ - Read-Only Sandbox  ││ - Isolated Workspace ││ - Isolated Workspace ││ - Isolated Workspace   │
│ - Repo Exploration   ││ - Feature Patching   ││ - Root-Cause Repair  ││ - Test Suite Gen & Run │
│ - Arch Findings      ││ - Change Proposals   ││ - Regression Fixes   ││ - Verification Evidence│
└──────────────────────┘└──────────────────────┘└──────────────────────┘└────────────────────────┘
```

---

## 3. Specialized Worker Agent Roles & Responsibilities

| Agent Role | Sandbox Mode | Tool Access | Assigned Responsibilities | Primary Outputs |
|---|:---:|---|---|---|
| **`ResearchAgent`** | Read-Only | `read_file`, `list_directory`, `search_files`, `git_status` | Explore repository structure, identify entry points, inspect dependencies, summarize architecture. | `FINDINGS` reports with file references. |
| **`CodingAgent`** | Isolated Sandbox | `read_file`, `create_file`, `apply_patch`, `list_directory` | Implement features, create models/endpoints, adhere to project conventions and skills. | `CHANGE_PROPOSAL` with unified diffs. |
| **`DebuggingAgent`** | Isolated Sandbox | `read_file`, `create_file`, `apply_patch`, `run_command` | Investigate failing tests or runtime exceptions, isolate root causes, propose minimal patches. | `CHANGE_PROPOSAL` with regression verification. |
| **`TestingAgent`** | Isolated Sandbox | `read_file`, `create_file`, `apply_patch`, `run_command` | Author unit and integration tests, verify edge cases, execute test suites, analyze outputs. | `REVIEW_REQUEST` with test execution evidence. |

---

## 4. Sidecar Runtime & Local IPC Architecture

The `SidecarRuntime` provides an isolated local execution environment for worker agents:

### 4.1 Local Asynchronous Message Broker
- Workers communicate strictly via the sidecar to the coordinator.
- Direct worker-to-worker instruction is prohibited. If the `TestingAgent` needs code adjustments, it emits a `REVIEW_REQUEST` or `FAILURE` to the coordinator, which dispatches a repair subtask to the `DebuggingAgent` or `CodingAgent`.

### 4.2 Bounded Model Inference Concurrency (`InferenceGate`)
To prevent GPU thrashing and out-of-memory crashes on host hardware:
```python
class InferenceGate:
    """Regulates local model inference requests across all active worker agents."""
    def __init__(self, max_concurrent: int = 1):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue = asyncio.Queue()

    async def acquire(self) -> None:
        await self._semaphore.acquire()

    def release(self) -> None:
        self._semaphore.release()
```
- Non-LLM activities (executing test suites, copying fixtures, computing diffs) execute freely in parallel.
- Actual model generation turns enter the `InferenceGate` queue, ensuring stable inference latency.

---

## 5. Inter-Agent Communication Protocol (IACP v1)

All messages exchanged within the multi-agent system adhere to a strict Pydantic schema:

```python
class MessageType(str, Enum):
    TASK_ASSIGNMENT = "task_assignment"
    TASK_ACCEPTED = "task_accepted"
    PROGRESS_UPDATE = "progress_update"
    FINDINGS = "findings"
    CHANGE_PROPOSAL = "change_proposal"
    TOOL_REQUEST = "tool_request"
    TOOL_RESULT = "tool_result"
    BLOCKED = "blocked"
    FAILURE = "failure"
    TASK_COMPLETED = "task_completed"
    REVIEW_REQUEST = "review_request"

class InterAgentMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: f"msg-{uuid.uuid4().hex[:8]}")
    task_id: str
    sender_agent: str      # e.g., "coordinator", "worker-coding-01"
    recipient: str         # e.g., "coordinator", "worker-research-01"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    message_type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
```

---

## 6. Workspace Isolation & Safe Integration Protocol

```
                     ┌──────────────────────────────────────────────┐
                     │          Primary Integration Tree            │
                     │             <workspace_root>                 │
                     └───────┬──────────────────────────────▲───────┘
                             │ Clone / Branch               │ Validate & Apply
                             ▼                              │ Approved Diffs
                     ┌──────────────────────┐       ┌───────┴──────────────┐
                     │   Worker Workspace   │       │ Integration Verifier │
                     │ .codemind/workspaces/│       │ - Detect file overlap│
                     │   <worker_id>/       │       │ - Verify syntax      │
                     └──────────────┬───────┘       │ - Execute tests      │
                                    │               └──────────────────────┘
                                    │ Produce
                                    ▼
                             ┌──────────────┐
                             │    Diff &    │
                             │ChangeProposal│
                             └──────────────┘
```

1. **Provisioning**: When a worker starts, the sidecar creates a clean isolated workspace mirror at `.codemind/workspaces/<worker_id>/`.
2. **Containment**: The worker's `WorkspaceSandbox` enforces path boundary containment inside `.codemind/workspaces/<worker_id>/`. Any attempt to traverse out is blocked.
3. **Change Proposal**: When coding or repair completes, the worker computes unified diffs of mutated files and submits a `CHANGE_PROPOSAL` message to the coordinator.
4. **Conflict Detection**:
   - Coordinator checks whether proposed mutated files intersect with pending proposals from other workers.
   - If conflicting edits to the same file are detected, the coordinator rejects the proposal, requests a rebase, or serializes the tasks.
5. **Integration & Final Verification**:
   - Approved patches are applied to the primary integration workspace.
   - `VerificationRunner` executes the automated test suite in the primary workspace before declaring the overall task `COMPLETED_VERIFIED`.

---

## 7. Shared Memory & Skills Integration

1. **Scoped Memory Delivery**: Workers do not receive the entire SQLite memory database. The coordinator queries `MemoryRetriever` and provides only relevant Layer A-D excerpts in the `TASK_ASSIGNMENT` payload.
2. **Worker Memory Proposals**: When a worker discovers a useful project decision or convention, it submits a memory update proposal. The coordinator validates it via `MemoryDistiller` and persists it to the central SQLite database.
3. **Role-Scoped Skill Injection**: The coordinator matches skills to worker roles:
   - `ResearchAgent` $\rightarrow$ `codebase-understanding`
   - `CodingAgent` $\rightarrow$ `python-backend`, `react-frontend`, `api-development`, `database-engineering`
   - `DebuggingAgent` $\rightarrow$ `debugging`
   - `TestingAgent` $\rightarrow$ `testing`

---

## 8. CLI Command Specifications

The CLI is extended with the `codemind agents` and `codemind sidecar` command groups:

```bash
codemind agents list              # List active and registered worker agents and their states
codemind agents status            # Display real-time status of multi-agent tasks
codemind agents inspect <id>      # Inspect worker role, assigned subtask, and message history
codemind agents stop <id>         # Terminate a running worker agent
codemind agents config            # View and adjust worker concurrency and turn limits
codemind agents logs <id>         # View audit event stream for a specific worker

codemind sidecar status           # Check sidecar runtime health, queue size, and active workers
codemind sidecar start            # Initialize local sidecar service
codemind sidecar stop             # Terminate sidecar service and running workers
```

---

## 9. Phase 7 Benchmark Suite Specification (`benchmarks/phase_7/`)

The evaluation harness will execute 15 scenarios (A through O) and a comparative study against Phase 6:

- **Scenario A**: Coordinator creates a correct task DAG with role assignments.
- **Scenario B**: Correct worker role assignment matching task intent.
- **Scenario C**: Research and Coding agents cooperate successfully.
- **Scenario D**: Debugging and Testing agents collaborate on test-driven repair.
- **Scenario E**: Multiple independent tasks execute in parallel without conflict.
- **Scenario F**: Detection and prevention of shared file modification conflicts.
- **Scenario G**: Isolated worker workspace boundary enforcement.
- **Scenario H**: Rejection of malformed and unauthorized inter-agent messages.
- **Scenario I**: Automatic worker crash recovery and task reassignment.
- **Scenario J**: Coordinator interruption and state restoration.
- **Scenario K**: Bounded inference concurrency under simultaneous worker demand.
- **Scenario L**: Worker cancellation and graceful shutdown.
- **Scenario M**: Shared memory and skill distribution across workers.
- **Scenario N**: End-to-end multi-agent software feature delivery.
- **Scenario O**: Comparative evaluation: Multi-Agent System vs Single-Agent Phase 6.
