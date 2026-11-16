# CodeMind Reliability — Regression Test Matrix

> **Verification Specification:** Required Hermetic & End-to-End Regression Gates  
> **Target:** Verification of Phase A Remediations  

---

## 1. Regression Test Suite Architecture

All reliability guarantees must be backed by automated hermetic regression tests located in `tests/reliability/`:

```text
tests/reliability/
├── test_completion_invariants.py    # Honest completion report & status evaluation
├── test_task_isolation.py           # Multi-task file attribution & ledger purity
├── test_protocol_hardening.py       # Response normalization & malformed handling
└── test_turn_budget_bounds.py       # Turn exhaustion, pause states & repair budgets
```

---

## 2. Test Cases & Acceptance Criteria

| Test ID | Module | Scenario | Input / Precondition | Expected Invariant & Outcome |
|---|---|---|---|---|
| **REL-01** | `test_completion_invariants` | Paused Task with Passing Checks | Task paused at turn limit (`is_paused=True`), but internal unit tests passed. | Status MUST evaluate to `PAUSED (TURN LIMIT REACHED)`. `verified` MUST be `False`. Never `VERIFIED SUCCESS`. |
| **REL-02** | `test_completion_invariants` | Incomplete Task with Missing Files | Model claims final completion, but expected created files do not exist on disk. | Status MUST evaluate to `FAILED (Missing expected files: ...)`. `verified` MUST be `False`. |
| **REL-03** | `test_completion_invariants` | Root Test Conflation Prevention | Task targets `documents/portfolio/`, but workspace has `run_tests.py` in root. | Verification runner must NOT execute root `run_tests.py` as user task verification. |
| **REL-04** | `test_task_isolation` | Consecutive Task File Purity | Session runs Task A (creates `app_a.py`), then Task B (creates `app_b.py`). | Task B completion report must list ONLY `app_b.py`. `app_a.py` MUST NOT appear in Task B's report. |
| **REL-05** | `test_task_isolation` | Checkpoint Contamination Guard | Incomplete checkpoint from previous task exists in `.codemind/checkpoints/`. | Starting a new unrelated task must NOT inherit files from the old checkpoint. |
| **REL-06** | `test_protocol_hardening` | Conversational Markdown Fencing | Model emits text preamble before and after a ```json ``` tool call block. | Protocol normalizer extracts JSON cleanly; dispatches valid `ToolCallAction` without error. |
| **REL-07** | `test_protocol_hardening` | Non-JSON Model Hallucination | Model emits pure conversational advice (e.g. "You should edit index.html"). | Evaluated as text or malformed action; strictly FORBIDDEN from triggering rogue tool calls. |
| **REL-08** | `test_turn_budget_bounds` | Repair Budget Decoupling | Model emits malformed response requiring 3 correction loopbacks. | Loopback corrections consume `repair_attempts`, NOT the primary task budget (turn count remains bounded). |
| **REL-09** | `test_turn_budget_bounds` | Clean Pause on Turn 20 | Task runs 20 turns without final completion. | State transitions cleanly to `PAUSED`. All plan states and file ledgers preserved. |

---

## 3. Execution & Verification Command

To run the dedicated reliability regression suite:

```bash
uv run --python 3.12 python -m unittest discover -s tests/reliability -p "test_*.py"
```

Exit condition for Phase A release gate: **9 / 9 reliability tests passing 100%**.
