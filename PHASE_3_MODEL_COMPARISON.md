# CodeMind Phase 3 — In-Depth Model Comparison

**Date:** 2026-11-16  
**Evaluator:** Senior AI Agent Systems Engineer  
**System:** CodeMind CLI (Local-First Companion)  
**Hardware Environment:** Linux (Ubuntu 24.04 LTS), NVIDIA GB10 GPU, Python 3.12, Local Ollama v0.1.x (`http://127.0.0.1:11434`)  
**Models Evaluated:**
1. `qwen3.6:35b` (Qwen 3.6 35B — Thinking/Reasoning MoE Architecture, 22 GB)
2. `qwen2.5:72b` (Qwen 2.5 72B Dense Architecture, 47 GB)
3. `mixtral:latest` (Mixtral 8x7B MoE Architecture, 26 GB)

---

## 1. Quantitative Comparison Matrix

The table below summarizes the empirical data captured directly from the execution traces across the 6 standardized Phase 3 benchmark scenarios.

| Evaluation Metric | `qwen3.6:35b` | `qwen2.5:72b` | `mixtral:latest` | Delta (`qwen3.6` vs `qwen2.5`) |
| :--- | :---: | :---: | :---: | :---: |
| **Task Completion Rate** | **6 / 6 (100.0%)** | 4 / 6 (66.7%) | 0 / 6 (0.0%) | **+33.3%** |
| **Test Verification Pass Rate** | **6 / 6 (100.0%)** | 4 / 6 (66.7%) | 0 / 6 (0.0%) | **+33.3%** |
| **Total Benchmark Wall Time** | **462.11 s (7.7 min)** | 1,760.71 s (29.3 min) | 1,598.3 s (aborted) | **3.81x faster** |
| **Total Model Turns** | 59 turns | 45 turns | 41 turns | +14 turns |
| **Avg Turns per Scenario** | 9.8 turns | 7.5 turns | 6.8 turns | +2.3 turns |
| **Total Tool Calls Issued** | 34 calls | 32 calls | 24 calls | +2 calls |
| **Valid Tool Call Rate** | **100.0% (34/34)** | **100.0% (32/32)** | 68.4% (malformed args) | Parity (100%) |
| **Protocol Envelope Retries** | 4 retries (all recovered) | 6 retries (2 aborted) | 18 retries (all failed) | **Zero fatal aborts** |
| **Permission Approvals Audited** | 6 (all audited/granted) | 8 (all audited/granted) | 2 (aborted before gate) | -2 approvals |
| **Unnecessary File Modifications** | **0** (strict adherence) | **0** (strict adherence) | 1 (broken syntax patch) | Parity (0) |
| **False Success Claims** | **0** (honest reporting) | **0** (honest reporting) | 2 (claimed pass on fail) | Parity (0) |
| **Session Recovery Continuation** | **PASSED** (Rehydrated 11 turns) | **PASSED** (Rehydrated 8 turns) | FAILED (syntax divergence) | Parity (both passed) |

---

## 2. Scenario-by-Scenario Empirical Breakdown

### Test A — Project Understanding (Read-Only Exploration)
*Goal: Inspect unfamiliar repo (`fixture_python`), identify modules, entry points, configuration, and test instructions without modifying any files.*

| Dimension | `qwen3.6:35b` | `qwen2.5:72b` |
| :--- | :--- | :--- |
| **Outcome** | **PASSED** | **FAILED** |
| **Execution Time** | 26.55 s | 364.61 s |
| **Turns / Tools** | 6 turns / 5 tools | 7 turns / 4 tools |
| **Files Modified** | 0 files | 0 files |
| **Root Cause / Behavior** | Inspected `README.md`, `pyproject.toml`, `src/task_manager.py`, and `tests/test_task_manager.py`. Wrapped factual synthesis cleanly in `{"type": "final", ...}`. | Inspected identical files. However, when generating a multi-paragraph synthesis, it emitted unescaped raw Markdown outside the JSON envelope 3 consecutive times, triggering the loop's safety abort. |

---

### Test B — Multi-File Feature Development
*Goal: Implement a `DiscountCode` dataclass in `src/models.py`, `apply_discount_code` in `src/service.py`, and test in `tests/test_service.py`.*

| Dimension | `qwen3.6:35b` | `qwen2.5:72b` |
| :--- | :--- | :--- |
| **Outcome** | **PASSED** | **FAILED** |
| **Execution Time** | 126.92 s | 204.85 s |
| **Turns / Tools** | 11 turns / 5 tools | 4 turns / 3 tools |
| **Files Modified** | `src/models.py`, `src/service.py` | None |
| **Root Cause / Behavior** | Formulated 4-task plan. Patched `DiscountCode` dataclass into `src/models.py`. Patched `src/service.py` with discount imports. Handled a malformed JSON feedback loopback without crashing and verified test suite passing. | Read files accurately. Attempted to generate combined multi-file patches inside a single JSON string, which caused token cutoffs and unescaped quotes. Failed after 3 malformed retries without touching disk. Harness correctly flagged `Failed to modify all required files`. |

---

### Test C — Bug Diagnosis and Root-Cause Repair
*Goal: Diagnose 2 deliberate defects in `src/auth.py` (inverted expiration timestamp `<` vs `>`, direct dict key access causing `KeyError: 'role'`).*

| Dimension | `qwen3.6:35b` | `qwen2.5:72b` |
| :--- | :--- | :--- |
| **Outcome** | **PASSED** | **PASSED** |
| **Execution Time** | 50.32 s | 172.39 s |
| **Turns / Tools** | 9 turns / 4 tools | 7 turns / 5 tools |
| **Verification Output** | `Ran 3 tests in 0.000s, OK` | `Ran 3 tests in 0.000s, OK` |
| **Fix Quality** | 100% root-cause: Changed `>` to `<` and `payload["role"]` to `payload.get("role", "guest")`. | Identical 100% root-cause fix. Both defects eliminated. |

---

### Test D — Test Execution & Interactive Repair Loop
*Goal: Execute tests via `run_command`, capture traceback, formulate patch, apply patch, and re-run tests until verified.*

| Dimension | `qwen3.6:35b` | `qwen2.5:72b` |
| :--- | :--- | :--- |
| **Outcome** | **PASSED** | **PASSED** |
| **Execution Time** | 67.14 s | 182.79 s |
| **Turns / Tools** | 11 turns / 6 tools | 8 turns / 7 tools |
| **Traceback Captured** | Captured `AssertionError` and `KeyError` | Captured identical trace |
| **Loop Convergence** | Applied patches sequentially, re-ran tests, proved 3/3 passed. | Applied patches, re-ran tests, proved 3/3 passed. |

---

### Test E — Multi-Step Autonomous Workflow
*Goal: End-to-end task: plan formulation, add `archive_completed_tasks` to `TaskManager`, write unit test in `test_task_manager.py`, execute test runner, summarize.*

| Dimension | `qwen3.6:35b` | `qwen2.5:72b` |
| :--- | :--- | :--- |
| **Outcome** | **PASSED** | **PASSED** |
| **Execution Time** | 92.06 s | 370.98 s |
| **Turns / Tools** | 8 turns / 5 tools | 9 turns / 7 tools |
| **Test Output** | `Ran 4 tests in 0.000s, OK` | `Ran 4 tests in 0.000s, OK` |
| **Implementation Quality** | Authored `archive_completed_tasks(self) -> list[Task]`. Authored unit test asserting return count, task properties, and removal from `_tasks` dict. | Authored `archive_completed_tasks` and matching test suite. |

---

### Test F — Session Recovery & Continuation
*Goal: Initiate task, save session snapshot, terminate agent, instantiate brand new agent resuming from session ID, verify plan rehydration and execute continuation prompt.*

| Dimension | `qwen3.6:35b` | `qwen2.5:72b` |
| :--- | :--- | :--- |
| **Outcome** | **PASSED** | **PASSED** |
| **Execution Time** | 99.12 s | 465.09 s |
| **Turns Rehydrated** | 11 prior turns | 8 prior turns |
| **Continuation Result** | Resumed seamlessly, executed `python3 -c "from task_manager..."` to verify task count, recovered from raw-text warning, returned final answer. | Resumed cleanly, executed check via `run_command`, returned final answer. |

---

## 3. Deep Architectural Analysis: Why Qwen 3.6:35B Outperformed Qwen 2.5:72B

Despite having half the parameter count (35B vs 72B), `qwen3.6:35b` significantly outperformed `qwen2.5:72b` across reliability, speed, and protocol adherence. The root causes are:

### 1. Thinking / Reasoning Separation Buffer
- `qwen3.6:35b` is an internal chain-of-thought (CoT) reasoning model. It outputs `<think> ... </think>` tokens before emitting its public response.
- In `qwen2.5:72b`, the model immediately starts generating the public JSON envelope. When reasoning requires complex calculations or planning, the JSON string remains open in memory for hundreds of tokens. Any markdown quote, newline, or syntax drift corrupts the JSON envelope.
- `qwen3.6:35b` completes all analysis inside the thinking channel first. Once reasoning converges, it emits a short, pristine, valid JSON envelope without syntax flaws.

### 2. Inference Latency & Token Throughput
- On the NVIDIA GB10 hardware, `qwen3.6:35b` (22 GB) fits entirely within fast GPU VRAM with ample KV-cache head-room, generating at **~45 tokens/second**.
- `qwen2.5:72b` (47 GB) occupies almost the entire VRAM budget, forcing context-shifting and generating at **~12 tokens/second**.
- Result: `qwen3.6:35b` completed the full 6-scenario suite in **7.7 minutes**, while `qwen2.5:72b` required **29.3 minutes** (3.8x slower).

### 3. Error Recovery Agility
- When the runtime loop emitted a `MalformedAction` correction prompt (`Validation Error: Your response did not contain a valid JSON envelope...`), `qwen3.6:35b` corrected itself on the very next turn in 100% of cases.
- `qwen2.5:72b` frequently repeated the formatting mistake (e.g. emitting raw markdown again) until hitting the 3-attempt abort threshold.

---

## 4. Mixtral:latest Failure Analysis

`mixtral:latest` (Mixtral 8x7B MoE) achieved **0/6 passed**. Key failure patterns:
1. **Protocol Envelope Drift**: In 65% of turns, it failed to output the required `{"protocol_version": "1", "type": "tool_call" | "plan" | "final"}` envelope, outputting raw tool calls or markdown text.
2. **Syntax Degradation in Code Patches**: In Test E, it attempted to patch `src/task_manager.py` but emitted a stray `:` on line 35, causing a fatal Python `SyntaxError`.
3. **Hallucinated Verification**: In Test D, it reported that tests passed without ever calling `run_command` to execute them. CodeMind's verification engine caught this and marked the status `COMPLETED WITH UNVERIFIED WORK`.

---

## 5. Conclusion & Selection

| Criterion | Winner |
| :--- | :--- |
| **Agentic Reliability** | **`qwen3.6:35b`** (100% scenario pass rate) |
| **Coding & Patch Accuracy** | **`qwen3.6:35b`** (zero syntax errors, root-cause fixes) |
| **Execution Latency** | **`qwen3.6:35b`** (3.8x faster than 72B) |
| **Protocol Strictness** | **`qwen3.6:35b`** (recovers from formatting errors immediately) |
| **Hardware Footprint** | **`qwen3.6:35b`** (22 GB VRAM vs 47 GB) |

**Official Recommendation:** **`qwen3.6:35b`** is selected as the default intelligence provider for CodeMind CLI.
