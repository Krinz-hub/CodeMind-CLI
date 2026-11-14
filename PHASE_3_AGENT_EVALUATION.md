# CodeMind Phase 3 — Real-World Agent Evaluation Report

**Date:** 2026-11-14  
**Evaluator:** Senior AI Agent Systems Engineer  
**System:** CodeMind CLI (Local-First Companion)  
**Host Environment:** Linux (Ubuntu 24.04 LTS), NVIDIA GB10, Python 3.12, Local Ollama v0.1.x (`http://127.0.0.1:11434`)  
**Security Policy:** Strict Workspace Boundaries, Symlink Escape Detection, Path Traversal Rejection, Audited Approval Gates for Execute & Shell actions.

---

## 1. Executive Summary & Capability Classification

CodeMind CLI has been subjected to a rigorous empirical evaluation on real-world software engineering benchmarks across 4 disposable projects and 6 core scenarios (Test A through Test F).

### Final Capability Level: **Level 4 — Verified Feature Development and Debugging** (with `qwen3.6:35b`)

| Capability Tier | Description | Demonstrated Status |
| :--- | :--- | :--- |
| **Level 0** | Model connected | Demonstrated across all local models (`qwen3.6:35b`, `qwen2.5:72b`, `mixtral:latest`). |
| **Level 1** | Basic tool usage | Demonstrated. High schema conformity, robust tool validation and output budgeting. |
| **Level 2** | Multi-step repository exploration | Demonstrated. Complete inspection of unfamiliar architectures and config files without mutations. |
| **Level 3** | Reliable file modification | Demonstrated. Safe unified diff patching (`apply_patch`) and CRLF normalization. |
| **Level 4** | **Verified feature development and debugging** | **Demonstrated.** Successfully diagnosed 2 subtle defects in auth, added complex multi-file features, and proved fixes via active test execution. |
| **Level 5** | Autonomous multi-step software engineering | Partially Demonstrated. Succeeded autonomously on Python suites with `qwen3.6:35b`, but larger workflows require enhanced self-correction on formatting errors. |

---

## 2. Quantitative Model Comparison

| Evaluation Metric | `qwen3.6:35b` (Recommended) | `qwen2.5:72b` | `mixtral:latest` |
| :--- | :---: | :---: | :---: |
| **Scenario Completion Rate** | **6 / 6 (100%)** | 4 / 6 (66.7%) | 0 / 6 (0.0%) |
| **Test Suite Pass Rate** | **100% (Passed A-F)** | 66.7% (Passed C, D, E, F) | 0% (Failed all verification suites) |
| **Total Benchmark Time** | **462.1 s (~7.7 min)** | 1,760.7 s (~29.3 min) | 1,598.3 s (aborted/failed) |
| **Valid Tool Call Rate** | **100% (34/34 calls)** | 100% (32/32 calls) | 68.4% (malformed syntax/arguments) |
| **Protocol Envelope Compliance** | **95.2%** (Fast self-recovery) | 71.4% (Aborted on long summaries) | 35.0% (Repeated formatting violations) |
| **Session Recovery (Test F)** | **PASSED** (Rehydrated 11 turns) | **PASSED** (Rehydrated 8 turns) | FAILED (Formatting divergence) |
| **Approvals Audited & Granted** | 4 (Strictly enforced) | 8 (Strictly enforced) | 2 (Enforced before syntax error) |

---

## 3. Detailed Scenario Breakdown

### Test A — Project Understanding (Unfamiliar Codebase)
- **qwen3.6:35b**: **PASSED** (26.55s, 6 turns, 5 tools). Identified `TaskManager`, `pyproject.toml`, test entrypoints, zero mutations.
- **qwen2.5:72b**: FAILED (364.61s). Gathered facts accurately but failed to wrap large synthesis in JSON envelope after 3 retries.
- **mixtral:latest**: FAILED. Exceeded turn limit without synthesizing architecture.

### Test B — Multi-File Feature Development
- **qwen3.6:35b**: **PASSED** (126.92s, 11 turns, 5 tools). Cleanly modified `src/models.py` (added `DiscountCode`), updated `src/service.py` (`apply_discount_code`), and verified tests.
- **qwen2.5:72b**: FAILED. Exceeded protocol envelope retries during large multi-file diff generation.
- **mixtral:latest**: FAILED. Failed to edit required files.

### Test C — Bug Diagnosis & Repair
- **qwen3.6:35b**: **PASSED** (50.32s, 9 turns, 4 tools). Diagnosed inverted timestamp comparison (`<` vs `>`) and unhandled `KeyError` in `extract_user_role`. Both 100% fixed, 3/3 tests passed.
- **qwen2.5:72b**: **PASSED** (172.39s, 7 turns, 5 tools). Diagnosed both defects correctly and applied clean patches. 3/3 tests passed.
- **mixtral:latest**: FAILED. Applied incomplete logic fix.

### Test D — Test Execution & Repair Loop
- **qwen3.6:35b**: **PASSED** (67.14s, 11 turns, 6 tools). Ran initial tests, captured traceback, applied fixes, re-ran tests, proved verified success.
- **qwen2.5:72b**: **PASSED** (182.79s, 8 turns, 7 tools). Executed tests, captured trace, fixed defects, verified completion.
- **mixtral:latest**: FAILED. Claimed completion without executing verification.

### Test E — Multi-Step Autonomous Workflow
- **qwen3.6:35b**: **PASSED** (92.06s, 8 turns, 5 tools). Created structured plan, added `archive_completed_tasks`, authored unit test `test_archive_completed_tasks`, verified all 4 tests passing.
- **qwen2.5:72b**: **PASSED** (370.98s, 9 turns, 7 tools). Authored method and tests, 4/4 passed.
- **mixtral:latest**: FAILED. Introduced syntax error in `task_manager.py`.

### Test F — Session Recovery & Continuation
- **qwen3.6:35b**: **PASSED** (99.12s, 14 turns, 9 tools). Saved checkpoint at turn 11, process killed and resumed by fresh agent instance, plan and state rehydrated, continued task cleanly.
- **qwen2.5:72b**: **PASSED** (465.09s, 10 turns, 6 tools). Successfully resumed from turn 8 and confirmed task counts.

---

## 4. Failure Classification & Root Cause Analysis

1. **Protocol Envelope Strictness on Large Outputs**: Non-thinking models like `qwen2.5:72b` struggle to escape nested JSON when producing 1,000+ token outputs. Thinking models (`qwen3.6:35b`) think before generating and reliably output pristine envelopes.
2. **Whitespace and Diff Drift**: Resolved via tolerant fuzzy hunking and CRLF normalization in `src/codemind/tools/patch.py`.
3. **Space Escaping in Paths**: When executing `run_command`, spaces in workspace paths (`/home/piet/Documents/codemind cli`) must be quoted. `qwen3.6:35b` self-corrected immediately.

---

## 5. Security & Permission Observations
- Sandbox correctly blocked path traversal (`../../etc/passwd`) and symlink escapes.
- All write and execution tools passed through `PermissionChecker`.
- In `TRUSTED` mode, execution of terminal shell commands strictly required interactive approval, which was audited and recorded in telemetry.

---

## 6. Recommendations & Roadmap to Phase 4
1. **Set `qwen3.6:35b` as Default Model**: It is by far the highest performing, fastest, and most reliable local model tested.
2. **Loosen Protocol Envelope for Non-Reasoning Models**: Add fallback extraction regex for raw Markdown codeblocks when models fail JSON formatting.
3. **Phase 4 Focus**: Advanced context pruning, multi-agent collaboration, and automated self-healing CI loops.
