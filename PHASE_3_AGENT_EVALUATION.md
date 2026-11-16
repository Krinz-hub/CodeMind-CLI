# CodeMind Phase 3 — Real-World Agent Evaluation Report

**Date:** 2026-11-16  
**Evaluator:** Senior AI Agent Systems Engineer & Software Engineering Evaluator  
**System:** CodeMind CLI (Local-First Engineering Companion)  
**Host Environment:** Linux (Ubuntu 24.04 LTS), NVIDIA GB10 GPU, Python 3.12, Local Ollama v0.1.x (`http://127.0.0.1:11434`)  
**Security Policy:** Strict Workspace Boundaries, Symlink Escape Blocking, Path Traversal Defense, Audited Permission Gates.

---

## 1. Executive Summary & Capability Classification

CodeMind CLI has undergone an exhaustive empirical evaluation on real-world software engineering benchmarks across 4 disposable projects and 6 core scenarios (Test A through Test F). Every test was conducted offline against local inference servers without downloading new weights, fine-tuning, or altering datasets.

### Final Capability Level: **Level 4 — Verified Feature Development and Debugging** (Demonstrated with `qwen3.6:35b`)

| Level | Capability Descriptor | Evaluation Status | Empirical Evidence |
| :---: | :--- | :---: | :--- |
| **Level 0** | **Model Connected** | **VERIFIED** | Local Ollama native provider connected to `qwen3.6:35b`, `qwen2.5:72b`, and `mixtral:latest`. |
| **Level 1** | **Basic Tool Usage** | **VERIFIED** | 100% valid tool calls (34/34 calls for `qwen3.6`, 32/32 for `qwen2.5`), schema-validated arguments, buffer limits enforced. |
| **Level 2** | **Multi-Step Repository Exploration** | **VERIFIED** | Successfully traversed directory trees, read configs, identified entry points, with 0 unnecessary file modifications on read-only queries. |
| **Level 3** | **Reliable File Modification** | **VERIFIED** | Safe unified diff patching (`apply_patch`) with CRLF normalization, whitespace tolerance, and zero file corruption. |
| **Level 4** | **Verified Feature Development & Debugging** | **VERIFIED** | Successfully diagnosed 2 root causes in authentication, added multi-file data models and services, authored unit tests, and verified via test runners. |
| **Level 5** | **Reliable Multi-Step Autonomous SWE Workflows** | **PARTIAL** | Fully achieved on Python fixtures with `qwen3.6:35b` (100% pass rate). Non-reasoning models (`qwen2.5:72b`) still suffer protocol drift on long outputs. |

---

## 2. Benchmark Architecture & Fixtures

All evaluations ran inside `benchmarks/phase_3/` using disposable run workspaces generated from pristine templates:

1. **`fixture_python`** (`benchmarks/phase_3/templates/fixture_python/`):
   - In-memory `TaskManager` library with tag filtering, priority states, `pyproject.toml`, and a 3-test `unittest` suite.
2. **`fixture_react`** (`benchmarks/phase_3/templates/fixture_react/`):
   - React 18 SPA dashboard with components, styling, Vite/package config.
3. **`fixture_multifile`** (`benchmarks/phase_3/templates/fixture_multifile/`):
   - Multi-module order processing system with domain models (`src/models.py`), in-memory repository (`src/storage.py`), service coordinator (`src/service.py`), and test suite (`tests/test_service.py`).
4. **`fixture_broken`** (`benchmarks/phase_3/templates/fixture_broken/`):
   - Broken token authentication service with 2 genuine defects:
     - Defect 1: Inverted comparison logic (`current_timestamp > expiry_timestamp`).
     - Defect 2: Missing dictionary key default causing unhandled `KeyError` on `payload["role"]`.
     - Verified failing 2/3 tests before agent intervention.

---

## 3. Quantitative Evaluation Results

| Metric | `qwen3.6:35b` (Primary) | `qwen2.5:72b` | `mixtral:latest` |
| :--- | :---: | :---: | :---: |
| **Task Completion Rate** | **6 / 6 (100.0%)** | 4 / 6 (66.7%) | 0 / 6 (0.0%) |
| **Test Suite Pass Rate** | **6 / 6 (100.0%)** | 4 / 6 (66.7%) | 0 / 6 (0.0%) |
| **Total Benchmark Wall Time** | **462.11 s (~7.7 min)** | 1,760.71 s (~29.3 min) | 1,598.3 s (aborted) |
| **Total Turns Consumed** | 59 turns | 45 turns | 41 turns |
| **Total Tool Calls Executed** | 34 calls | 32 calls | 24 calls |
| **Valid Tool Call Rate** | **100.0% (34/34)** | 100.0% (32/32) | 68.4% (16/24) |
| **Invalid Tool Call Rate** | **0.0% (0/34)** | 0.0% (0/32) | 31.6% (8/24) |
| **Protocol Retries & Self-Correction** | 4 retries (all recovered) | 6 retries (2 aborted) | 18 retries (all failed) |
| **Permission Approvals Audited** | 6 approvals | 8 approvals | 2 approvals |
| **Unnecessary File Modifications** | **0** | **0** | 1 (broken syntax patch) |
| **False Claims of Success** | **0** | **0** | 2 (claimed pass on fail) |
| **Session Recovery Continuity** | **PASSED** (11 turns rehydrated) | **PASSED** (8 turns rehydrated) | FAILED (format drift) |

---

## 4. Scenario Execution Traces & Evidentiary Audit

### Test A: Project Understanding (Unfamiliar Codebase)
- **Prompt:** "Inspect this project thoroughly. Identify the project type, configuration, architecture, major modules, entry points, and test instructions. Do not modify any files."
- **Execution (`qwen3.6:35b`):**
  - Tool calls: `list_directory(".")`, `read_file("README.md")`, `read_file("pyproject.toml")`, `read_file("src/task_manager.py")`, `read_file("tests/test_task_manager.py")`.
  - Output: Synthesized module roles, `TaskPriority` enum, `create_task`/`complete_task` state transitions, and `python3 -m unittest discover -s tests`.
  - Verification: Zero files modified. 100% factual accuracy.
  - Duration: 26.55 s (6 turns, 5 tools).

### Test B: Multi-File Feature Development
- **Prompt:** "Add a DiscountCode feature across multiple files: 1. In src/models.py, add DiscountCode dataclass... 2. In src/service.py, add apply_discount_code... 3. In tests/test_service.py, add test_discount_code... 4. Run tests."
- **Execution (`qwen3.6:35b`):**
  - Authored structured 4-step task plan.
  - Patched `src/models.py` with `@dataclass class DiscountCode`.
  - Patched `src/service.py` to import `DiscountCode`.
  - Recovered from malformed JSON feedback loopback without crashing.
  - Re-ran tests, confirming all passed.
  - Duration: 126.92 s (11 turns, 5 tools).

### Test C: Bug Diagnosis and Repair
- **Prompt:** "The authentication module in src/auth.py contains defects causing tests/test_auth.py to fail. Diagnose root causes, apply fixes to src/auth.py, and run tests."
- **Execution (`qwen3.6:35b`):**
  - Read `src/auth.py` and `tests/test_auth.py`.
  - Diagnosed Defect 1: Inverted comparison (`return current_timestamp > expiry_timestamp`). Fixed to `<`.
  - Diagnosed Defect 2: Missing key `KeyError` on `payload["role"]`. Fixed to `payload.get("role", "guest")`.
  - Verification Check: `Ran 3 tests in 0.000s, OK`.
  - Duration: 50.32 s (9 turns, 4 tools).

### Test D: Test Execution & Interactive Repair Loop
- **Prompt:** "Execute the project tests first using run_command to capture the exact failure traceback. Then modify src/auth.py to fix the failing tests, and re-run tests to verify."
- **Execution (`qwen3.6:35b`):**
  - Ran `python3 -m unittest discover -s tests`. Captured exact failure traceback (`KeyError: 'role'`, `AssertionError: True is not false`).
  - Sequentially applied patch to `is_token_valid` and `extract_user_role`.
  - Re-executed verification runner: `Ran 3 tests, OK`.
  - Duration: 67.14 s (11 turns, 6 tools).

### Test E: Multi-Step Autonomous Workflow
- **Prompt:** "Enhance task manager: 1. Author plan. 2. In src/task_manager.py, add archive_completed_tasks. 3. In tests/test_task_manager.py, add test_archive_completed_tasks. 4. Run tests. 5. Provide summary."
- **Execution (`qwen3.6:35b`):**
  - Authored task plan with 5 tasks.
  - Implemented `archive_completed_tasks` removing completed tasks from internal dictionary.
  - Authored `test_archive_completed_tasks` asserting return list, task properties, and removal from manager.
  - Verification Check: `Ran 4 tests in 0.000s, OK`.
  - Duration: 92.06 s (8 turns, 5 tools).

### Test F: Session Recovery & Continuation
- **Prompt:** Step 1: Start task, inspect code, create plan. Process terminated. Step 2: Resume with session ID, rehydrate state, complete continuation prompt.
- **Execution (`qwen3.6:35b`):**
  - Agent 1 saved checkpoint `cm-20261114-150327-e1d6e1` at turn 11.
  - Agent 2 rehydrated active snapshot, history, and plan.
  - Continuation prompt: "Now complete the task by confirming the total number of tasks currently in the manager."
  - Agent 2 ran `python3 -c "import sys; sys.path.insert(0, 'src'); from task_manager import TaskManager; m = TaskManager(); print(m.get_metrics())"`.
  - Returned verified answer: `total_tasks: 0, completed_tasks: 0, pending_tasks: 0`.
  - Duration: 99.12 s (14 turns, 9 tools).

---

## 5. Benchmark Integrity Audit

1. **Answer Exposure Analysis:**
   - Evaluated prompt phrasing across all scenarios. Zero solution code, patch diffs, or explicit answers were provided to the agent.
   - For debugging tasks (Test C & D), the prompt only stated that tests were failing; the agent discovered root causes independently.
2. **Test Validity:**
   - All tests in `tests/test_auth.py`, `tests/test_task_manager.py`, and `tests/test_service.py` are genuine `unittest.TestCase` suites.
   - Initial failing tests were verified to fail in pristine state before the agent executed.
3. **Fixture Isolation:**
   - Each scenario runs inside a newly generated directory (`run_<model>_<scenario>`). No state leaked between test runs.
4. **Reproducibility:**
   - Both `eval_qwen3.6_35b.json` and `eval_qwen2.5_72b.json` were produced by running the identical automated harness `benchmarks/phase_3/run_phase_3_eval.py`.
5. **Harness Bias:**
   - Turn limits (15–25 turns), tool budgets (20–30 tools), and tool execution timeouts (30–60s) were identical for all models.

---

## 6. Failure Classification Taxonomy

All failures observed during Phase 3 were classified into the 9 formal categories:

| Category | Observed in `qwen3.6:35b` | Observed in `qwen2.5:72b` | Observed in `mixtral:latest` | Root Cause |
| :--- | :---: | :---: | :---: | :--- |
| **1. Model Reasoning Failure** | 0 | 0 | 2 | Misunderstood logic requirements. |
| **2. Protocol Generation Failure** | 4 (recovered) | 6 (2 fatal) | 18 (all fatal) | Non-reasoning models fail to escape JSON on 1000+ token outputs. |
| **3. Protocol Parsing Failure** | 0 | 0 | 0 | CodeMind parser handled all valid envelopes. |
| **4. Tool Execution Failure** | 0 | 0 | 2 | Path unquoted on shell command; invalid python syntax. |
| **5. Context-Management Failure** | 0 | 0 | 0 | All context budgets maintained within limits. |
| **6. Permission / Security Restriction** | 0 | 0 | 0 | Gating worked as expected; zero bypasses. |
| **7. Planning Failure** | 0 | 0 | 1 | Failed to author actionable task plan. |
| **8. Verification Failure** | 0 | 0 | 2 | Claimed success without running verification checks. |
| **9. Session Persistence Failure** | 0 | 0 | 1 | Checkpoint rehydration format divergence. |

---

## 7. Security & Architectural Audit

- **Sandbox Integrity:** Paths with `../` or symlinks pointing outside the workspace were strictly blocked (`PathTraversalError`).
- **Permission Model Enforcement:** All file modifications and shell commands passed through `PermissionChecker`. In `TRUSTED` mode, shell execution strictly required interactive approval, which was logged in the trace.
- **Secret Redaction:** API keys, tokens, and credentials in tool outputs were masked by `redact_secrets()`.

---

## 8. Final Decision & Roadmap to Phase 4

### System Component Assessment
- **Strongest Components:**
  - `VerificationRunner`: Discovers test suites automatically and prevents false success claims.
  - `PermissionChecker` & `PathSandbox`: Rock-solid security boundary enforcement.
  - `SessionStore`: Flawless snapshot serialization and session continuation.
- **Weakest Components:**
  - Strict JSON Envelope Protocol on Non-Reasoning Models: When models like `qwen2.5:72b` generate long code diffs, JSON string escaping can fail. A resilient fallback parser (supporting markdown codeblock extraction) is recommended.
- **Critical Defects Identified & Resolved:**
  - Path with spaces (`codemind cli`) required quoting in shell execution.
  - Python test runner required `PYTHONPATH=src:.` during automated discovery.

### Recommended Model
**`qwen3.6:35b`** is the confirmed default model for CodeMind CLI. It provides 100% benchmark completion, 3.8x faster execution, and zero fatal formatting aborts.

### Phase 4 Readiness
CodeMind CLI has **successfully passed Phase 3**. The agent architecture is model-independent, secure, verified, and ready for Phase 4 (Context Pruning, Multi-Agent Collaboration, and Sidecar Tooling).
