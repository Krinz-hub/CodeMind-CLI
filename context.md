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
- Created `PHASE_3_AGENT_EVALUATION.md`.

---

## 3. How to Run & Verify on Another Machine

1. **Verify Test Suite**:
   ```bash
   python3 run_tests.py
   ```
2. **Launch CLI**:
   ```bash
   python3 -m codemind.cli.main --help
   codemind models list
   ```
3. **Switch Model**:
   ```bash
   codemind models use qwen3.6:35b
   ```
4. **Execute an Agent Task**:
   ```bash
   codemind "Inspect the project and explain its architecture"
   ```

---

## 4. Next Steps for Phase 4

- Present `PHASE_3_AGENT_EVALUATION.md` to user.
- Consult `/home/piet/Documents/dev/CodeMind_CLI_Agent_Build_Specification.md` for Phase 4 requirements (Context Pruning, Multi-Agent Coordination, or Tool Ecosystem expansion).
- Preserve the model adapter interface so proprietary CodeMind weights can plug in seamlessly.
