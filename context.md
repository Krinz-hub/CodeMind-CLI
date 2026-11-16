# CodeMind CLI — Handover Context & State Architecture

> **Purpose:** This file preserves the full context, architectural rules, implementation state, and technical history of this project so that any AI assistant (including Antigravity on another machine) can resume work immediately without hallucination or loss of fidelity.

---

## 1. Project Identity & Architecture

**CodeMind CLI** is an autonomous, local-first coding assistant and CLI agent. It is designed to work with locally hosted LLMs (Ollama, vLLM, llama.cpp, OpenAI-compatible local APIs) and will eventually host our proprietary CodeMind foundation model.

### Key Architectural Layers:
1. **CLI Layer (`src/codemind/cli/`)**:
   - Built on `Typer` & `Rich`.
   - Custom `CodeMindGroup` in `main.py` routes raw prompt strings directly to the hidden `ask` command while preserving subcommands (`codemind models ...`, `codemind status`, etc.).
   - Brand persona: **Milo**, an honest, rigorous engineering companion.

2. **Runtime Loop (`src/codemind/runtime/`)**:
   - `AgentLoop` in `loop.py`: Bounded execution loop with explicit turn limits (`max_turns`), tool call budgets (`max_tool_calls`), and timeout protections.
   - Self-correcting feedback loop: Invalid responses trigger structured `MalformedAction` correction prompts rather than crashing.

3. **Protocol v1 (`src/codemind/models/protocol.py`)**:
   - Envelope structure:
     - `{"type": "action", "action": "tool", "tool": "<name>", "arguments": {...}, "reason": "..."}`
     - `{"type": "action", "action": "plan", "tasks": [...], "reason": "..."}`
     - `{"type": "action", "action": "final", "content": "...", "summary": [...]}`

4. **Model Adapters (`src/codemind/models/`)**:
   - `base.py`: Abstract `ModelAdapter`.
   - `ollama.py`: Native Ollama HTTP client (`/api/chat` and `/api/tags`).
   - `codemind_local.py`: Future custom CodeMind inference server adapter.
   - `mock.py`: Deterministic mock adapter for offline testing.
   - `discovery.py` & `evaluator.py`: Auto-discovers local models and runs 7-point capability tests.

5. **Tool Registry (`src/codemind/tools/`)**:
   - `filesystem.py`: `read_file`, `write_file`, `list_directory`, `file_search`.
   - `patch.py`: `apply_patch` supporting unified diffs and target/replacement with CRLF tolerance.
   - `terminal.py`: `run_command` with timeouts and buffer capping.
   - `git.py`: `git_status`, `git_diff`.

6. **Security & Sandbox (`src/codemind/security/`)**:
   - `sandbox.py`: Enforces workspace boundaries, canonicalizes paths, catches traversal and symlink escapes.
   - `permissions.py`: 3 modes (`supervised`, `trusted`, `read_only`). In `trusted`, safe file edits are auto-approved, but shell commands strictly require user approval.
   - `redaction.py`: Automatically masks API keys, bearer tokens, and private keys.

7. **Verification Engine (`src/codemind/verification/`)**:
   - `runner.py`: Discovers test runners (`pytest`, `unittest`, `npm test`, etc.) and executes checks with `PYTHONPATH=src:.`.
   - `reporter.py`: Enforces honest completion — agent never claims success without running checks.

8. **Session & Persistence (`src/codemind/sessions/`)**:
   - Checkpoints state, history, and task plans to `.codemind/sessions/<session_id>.json`.
   - Supports seamless session resumption: `codemind --resume <session_id>`.

---

## 2. Completed Milestones

### Phase 0: Repository Audit
- Fully audited codebase, identified Click/Typer command collisions, and normalized test runners.

### Phase 1: Foundational Agent Runtime & Offline Test Suite
- Built and verified complete 46-test offline test suite in `run_tests.py`.
- **Command to verify:** `python3 run_tests.py` (Must pass 46/46 tests).

### Phase 2: Local Model Integration
- Implemented model discovery, configuration, and model management CLI:
  - `codemind models`
  - `codemind models list`
  - `codemind models status`
  - `codemind models use <model>`
  - `codemind models test <model>`
- Evaluated local Ollama models on host machine (`qwen3.6:35b`, `qwen2.5:72b`, `mixtral:latest`).
- Created `LOCAL_MODEL_INTEGRATION.md`.

### Phase 3: Real-World Agent Evaluation
- Created benchmark fixtures in `benchmarks/phase_3/`:
  - `fixture_python` (in-memory TaskManager)
  - `fixture_react` (React dashboard SPA)
  - `fixture_multifile` (order processing domain)
  - `fixture_broken` (auth service with 2 deliberate bugs)
- Built automated harness `benchmarks/phase_3/run_phase_3_eval.py` running 6 scenarios (Test A through Test F).
- Empirical results:
  - **`qwen3.6:35b`**: **6/6 PASSED (100%)** — Level 4 Capability verified.
  - **`qwen2.5:72b`**: **4/6 PASSED (66.7%)** — Strong on repair & workflows.
  - **`mixtral:latest`**: **0/6 PASSED** — Repeated envelope violations & syntax bugs.
- Created `PHASE_3_AGENT_EVALUATION.md` and `PHASE_3_MODEL_COMPARISON.md`.

### Phase 4: Persistent Project Memory System
- Implemented local-first persistent project memory across 4 semantic tiers:
  - **Layer A (Project Memory):** Stable identity, tech stack, architecture, entry points, test commands.
  - **Layer B (Decision Memory):** Architectural Decision Records (ADRs) with rationale and rejected alternatives.
  - **Layer C (Task Memory):** Completed work, verified bugfixes, unresolved debt, and limitations.
  - **Layer D (Instruction Memory):** Workspace-level directives and persistent user coding preferences.
- Engine: Built on **SQLite 3 + FTS5** at `<workspace_root>/.codemind/memory/project_memory.db` with WAL mode.
- Subsystems:
  - `MemoryRetriever`: Multi-stage BM25 scoring with character budgeting (~6,000 chars) and staleness detection.
  - `MemoryDistiller`: Automated post-task extraction of verified accomplishments and user directives.
  - `Secret Shield Gate`: Scrubbed credentials (`sk-...`, `ghp_...`, Bearer tokens) across SQLite and FTS tables.
  - CLI: `codemind memory status`, `show`, `search <q>`, `list`, `update <id>`, `rebuild`, `clear`.
- Benchmarks: `benchmarks/phase_4/run_phase_4_eval.py` running 10 real-world scenarios (A through J).
  - Empirical result with `qwen3.6:35b`: **10/10 PASSED (100.0%)** in 56.43s.
- Created deliverables: `PHASE_4_ARCHITECTURE.md`, `PHASE_4_IMPLEMENTATION.md`, `PHASE_4_MEMORY_EVALUATION.md`, and `benchmarks/phase_4/RESULTS/`.

### Phase 5: Dynamic Skills Discovery, Selection and Execution Engine
- Implemented model-independent skills framework in standard markdown (`SKILL.md`) with YAML frontmatter.
- Schema & Model:
  - `SkillManifest` with strict kebab-case names, SemVer, trigger descriptors (manifests, globs, keywords), workflow steps, constraints, dependencies, conflicts, and verification specs.
- Multi-Tier Discovery Hierarchy:
  - `Project-Level` (`<workspace_root>/.codemind/skills/`) > `User-Level` (`~/.codemind/skills/`) > `Built-in` (`src/codemind/skills/builtin/`).
  - Project skills override lower-tier skills with identical names.
- 10 Built-in Starter Skills:
  - `python-backend`, `react-frontend`, `react-native-expo`, `api-development`, `database-engineering`, `debugging`, `testing`, `ui-ux-design`, `git-workflow`, `codebase-understanding`.
- Two-Stage Selection Engine:
  - Stage 1: Multi-signal pre-filtering (manifest triggers, intent keyword matching, project type, Layer A memory grounding). Null matching on generic non-code tasks avoids hallucinated skills.
  - Stage 2: Prerequisite dependency expansion (e.g., `react-native-expo` -> `react-frontend`) and conflict suppression with tier precedence.
- Untrusted Skill Security Invariant:
  - Skills provide advisory prompt guidance, never elevated permissions or script execution privileges.
  - Workspace sandbox (`WorkspaceSandbox`) and terminal permissions remain strictly authoritative.
- Context Budgeting:
  - Active skills formatted into system prompt strictly bounded at 5,000 characters (~1,250 tokens).
- CLI Suite:
  - `codemind skills list`, `show <name>`, `search <query>`, `validate`, `enable <name>`, `disable <name>`, `inspect`.
- Benchmark Evaluation (`benchmarks/phase_5/run_phase_5_eval.py`):
  - 13/13 scenarios passed (100.0% pass rate) in 129.86s with `qwen3.6:35b`.
  - A/B comparison demonstrated 42.8% reduction in turns (8 vs 14) and 66.7% fewer tool calls (2 vs 6) with skills enabled.
- Created deliverables: `PHASE_5_ARCHITECTURE.md`, `PHASE_5_IMPLEMENTATION.md`, `PHASE_5_SKILL_EVALUATION.md`, and `benchmarks/phase_5/RESULTS/`.

### Phase 6: Advanced Autonomy and Workflow Orchestration
- Implemented long-running software engineering orchestrator (`WorkflowOrchestrator` in `src/codemind/orchestration/`):
  - Hierarchical Directed Acyclic Graph (DAG) task decomposition (`HierarchicalTask`, `TaskPlan`, `TaskStatus`).
  - 10 explicit task states: `PENDING`, `READY`, `RUNNING`, `WAITING_FOR_APPROVAL`, `BLOCKED`, `FAILED`, `RETRYING`, `VERIFYING`, `COMPLETED`, `CANCELLED`.
  - Verification criteria invariant: No task marked `COMPLETED` without satisfying tangible verification criteria.
  - Topological scheduling with DFS cycle detection and priority dispatch.
- Intelligent Failure Recovery Engine (`src/codemind/orchestration/recovery.py`):
  - 10-category failure classifier (`FailureClassifier`) mapping errors to deterministic recovery actions (`TEST_DRIVEN_REPAIR`, `BUILD_REPAIR`, `LOOPBACK_CORRECTION`, `REFRESH_FILE_CONTEXT`, `VERIFY_DISK_OUTCOME`, `REPLAN`, `TERMINATE_GRACEFULLY`).
  - Strict permission invariant: Denied permissions are never retried. Non-idempotent operations verify disk state before repeating.
- Atomic Checkpoint Store (`src/codemind/orchestration/checkpoint.py`):
  - Two-stage atomic write protocol (`tmp.<pid>` -> `fsync` -> `os.replace`) preserving plan, completed/pending/failed tasks, observations, diffs, and execution positions under `.codemind/checkpoints/`.
- Concurrency Control (`src/codemind/orchestration/concurrency.py`):
  - Detects shared mutable file overlaps and read/write conflicts; dispatches safe independent tasks concurrently.
- Configurable Execution Budgets (`ExecutionBudget`):
  - Governs max turns, max tool calls, retries, timeout, concurrency, and file mutations.
- CLI Management Suite (`codemind task`):
  - `codemind task status`, `inspect <id>`, `pause <id>`, `resume <id>`, `cancel <id>`, `history`.
- Benchmark Evaluation (`benchmarks/phase_6/run_phase_6_eval.py`):
  - 15/15 scenarios passed (100.0% pass rate) in 315.91s with `qwen3.6:35b`.
  - Comparative evaluation confirmed formal DAG decomposition, atomic checkpoints (5 vs 1), and per-stage verification gates.
- Created deliverables: `PHASE_6_ARCHITECTURE.md`, `PHASE_6_IMPLEMENTATION.md`, `PHASE_6_EVALUATION.md`, and `benchmarks/phase_6/RESULTS/`.

---

### Phase 7: Multi-Agent Collaboration and Sidecar Runtime
- Transformed CodeMind from a single-agent orchestrator into a coordinated multi-agent software engineering system:
  - **`MultiAgentCoordinator`**: Supreme coordinator handling task decomposition, dynamic DAG construction, role assignment, conflict resolution, and central verification.
  - **IACP v1 Protocol**: Versioned structured message schema (`InterAgentMessage`) enforced by `MessageRouter` with coordinator supremacy (peer-to-peer bypasses and unauthorized delegations rejected).
  - **Specialized Worker Roles**:
    - `ResearchWorker`: `READ_ONLY` reconnaissance, codebase analysis, emits `FINDINGS`.
    - `CodingWorker`: Feature implementation in isolated sandboxes, emits `ChangeProposal` with diffs.
    - `DebuggingWorker`: Root cause isolation and targeted minimal repairs.
    - `TestingWorker`: Test suite authoring (AAA pattern) and regression execution, emits `REVIEW_REQUEST`.
  - **Isolated Worker Sandboxes (`WorkerWorkspaceManager`)**:
    - Cloned workspace mirrors under `.codemind/workspaces/<worker_id>/`.
    - Automated unified diff extraction and conflict detection prior to integration.
    - Zero unapproved edits touch the primary repository.
  - **Hardware Resource Governance (`InferenceGate`)**:
    - Asynchronous semaphore (`max_concurrent_inferences=1`) bounds LLM generation concurrency to shield local GPU/VRAM from exhaustion while non-inference tasks run in parallel.
  - **CLI Management**:
    - `codemind agents list`, `status`, `config`, `inspect <id>`, `stop <id>`, `logs <id>`
    - `codemind sidecar status`, `start`, `stop`, `workers`
- **Benchmark Evaluation (`benchmarks/phase_7/run_phase_7_eval.py`)**:
  - Evaluated 15 comprehensive scenarios (A through O) against `qwen3.6:35b`.
  - Result: **15/15 PASSED (100.0%)** in 332.87s.
  - Offline test suite expanded to **91 tests** (100% passing in 1.62s).
- Deliverables: `PHASE_7_ARCHITECTURE.md`, `PHASE_7_IMPLEMENTATION.md`, `PHASE_7_EVALUATION.md`.

---

### Phase 8: Custom Model Integration & Runtime Compatibility
- Designed and implemented model-independent custom foundation model integration:
  - **`CodeMindCustomAdapter` (`src/codemind/models/custom.py`)**:
    - Communicates over standard OpenAI-compatible endpoints (`/v1/chat/completions`, `/v1/models`).
    - Service health & signature discrimination: Checks `/health` and catches foreign non-LLM services (e.g. Godot AI Agent Desktop Service on port 8000) to prevent false readiness claims.
    - Preflight context window enforcement against model budget limits (`context_window` parameter).
  - **`FallbackAwareModelAdapter`**:
    - Transparently routes inference requests to fallback provider (`qwen3.6:35b` via local Ollama) if primary `codemind-custom` service is unreachable or unhealthy.
    - Captures detailed telemetry in `fallback_history` without masking underlying provider states or reporting false active status.
  - **`ProtocolNormalizer`**:
    - Robust extraction of Protocol v1 action envelopes from raw model outputs.
    - Strips `<think>...</think>` chain-of-thought blocks, unpacks markdown JSON fences (` ```json `), handles empty outputs with recovery templates, and normalizes unstructured text into valid `FinalAction` structures.
  - **CLI Updates (`src/codemind/cli/models_cli.py`)**:
    - Added `codemind models compare` subcommand for head-to-head evaluation across models.
    - Updated `codemind models status` to report fallback chains and health diagnostics.
- **Benchmark Evaluation (`benchmarks/phase_8/run_phase_8_eval.py`)**:
  - Evaluated 15 comprehensive capability categories (A through O) across `qwen3.6:35b`, `codemind-custom` (with fallback), and `mock`:
    - Protocol compliance, Project understanding, Repo exploration, Tool selection, Tool arguments, Single-file generation, Multi-file generation, Feature implementation, Bug diagnosis, Bug repair, Test generation, Test failure recovery, Long context, Multi-agent coordination, End-to-end feature delivery.
  - Result: **15/15 PASSED (100.0%)** in 159.05s.
  - Test suite expanded from 91 to **103 hermetic tests** (100% passing in ~1.8s).
- **Deliverables Produced**:
  - `PHASE_8_ARCHITECTURE.md`
  - `PHASE_8_IMPLEMENTATION.md`
  - `PHASE_8_MODEL_COMPATIBILITY.md`
  - `PHASE_8_EVALUATION.md`
  - `PHASE_8_FAILURE_ANALYSIS.md`
  - `benchmarks/phase_8/RESULTS/phase_8_evaluation.json` & `summary.json`

### One-Command Global Launcher & System Diagnostics
- Implemented universal global CLI launcher architecture (`src/codemind/launcher.py`):
  - **Auto-Discovery Hierarchy**: Automatically locates virtual environments via `CODEMIND_VENV`, `<repo_root>/.venv`, `~/.codemind/venv`, or local share directories.
  - **In-Place Re-Execution**: Re-executes commands under virtualenv Python via `os.execve`, preserving TTY streams, CLI arguments, and working directory without requiring manual `.venv` activation.
  - **Safe Local Model Lifecycle (`src/codemind/models/service_manager.py`)**: Automatically checks Ollama or custom model connectivity on startup; safely initiates `ollama serve` if offline and flags unpulled models.
  - **Comprehensive Diagnostics (`codemind doctor`)**: Evaluates 18 health checks across Python environment, required dependencies, CLI packaging, local inference services, and workspace tools.
  - **Packaging & Installation**: Added `./install.sh`, `codemind install` command, `src/codemind/__main__.py`, updated `pyproject.toml`, and authored `docs/INSTALLATION.md`.
  - **Test Suite**: Expanded to **111 tests** (`111/111 passed` in 1.9s).

---

## 3. How to Run & Verify on Another Machine

1. **Verify Offline Test Suite (111 Hermetic Tests)**:
   ```bash
   python3 run_tests.py
   ```
2. **One-Command Installation & Health Verification**:
   ```bash
   ./install.sh
   codemind doctor
   ```
3. **Launch CLI Globally from Any Directory**:
   ```bash
   codemind
   codemind --help
   codemind --version
   codemind status
   codemind models list
   codemind models compare
   codemind agents list
   codemind sidecar status
   codemind task status
   codemind skills list
   codemind memory show
   ```
3. **Run Benchmark Suites**:
   ```bash
   python3 benchmarks/phase_4/run_phase_4_eval.py
   python3 benchmarks/phase_5/run_phase_5_eval.py
   python3 benchmarks/phase_6/run_phase_6_eval.py
   python3 benchmarks/phase_7/run_phase_7_eval.py
   python3 benchmarks/phase_8/run_phase_8_eval.py
   ```
4. **Execute an Autonomous Multi-Agent Workflow**:
   ```bash
   codemind "Implement a TokenBucket rate limiter in src/limiter.py and create tests in tests/test_limiter.py"
   ```

---

## 4. Current Status & Next Steps

- **Current Autonomy Level:** Level 3.5 / 5.0 (Custom Model Adapter Foundation with Protocol Normalization & Observable Local Fallback; Level 4.2 when fully backed by active `qwen3.6:35b`).
- **Phase 8 Complete:** All 15 benchmark scenarios verified (100.0% pass rate in 159.05s), 103 unit/integration tests passing cleanly.
- **Phase 9 Readiness:** All Phase 8 requirements satisfied. Execution stops here per system instructions to present deliverables and await user approval before initiating Phase 9.
