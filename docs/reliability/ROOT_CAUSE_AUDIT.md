# CodeMind Reliability — Root Cause Audit & Failure Analysis

> **Incident Analysis:** Failure of React Portfolio Request and Resulting Invariants  
> **Document Status:** Authoritative Architectural Diagnosis  

---

## 1. Executive Summary of Observed Failure

During an end-to-end user request ("Make me a portfolio using React"), the following cascade of runtime failures was recorded:

1. **Protocol Breakdown:** Model response parser reported `Malformed model response`.
2. **Turn Exhaustion:** The execution loop reached its 20-turn limit and was forced to pause.
3. **Artifact Contamination:** The completion summary listed unrelated files from previous tasks (`documents/flappy_bird/` and `documents/insta_gram/`).
4. **Conflated Verification:** The verification engine discovered and ran `python3 run_tests.py`, executing CodeMind CLI's internal 123-test unit suite.
5. **False Success Inversion:** Because CodeMind's internal test suite passed, the system rendered `Final Verified Status: VERIFIED SUCCESS` to the user, despite zero React portfolio deliverables being completed.

---

## 2. Root Cause Audit by Subsystem

### Defect 1: The False Success Status Inversion
* **Source Locations:**
  - [`src/codemind/verification/reporter.py#L73-L82`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/verification/reporter.py#L73-L82)
  - [`src/codemind/orchestration/orchestrator.py#L293-L315`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/orchestration/orchestrator.py#L293-L315)
  - [`src/codemind/multiagent/coordinator.py#L357-L373`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/multiagent/coordinator.py#L357-L373)
* **Root Cause Mechanism:**
  In `HonestCompletionReport.evaluate_status()`, the presence of passing test checks unconditionally overrides task completion status:
  ```python
  # Current flawed logic in reporter.py:
  if self.checks:
      failed_checks = [c for c in self.checks if not c.passed]
      if failed_checks:
          return f"{CompletionStatus.FAILED.value} ...", False
      else:
          self.verified = True
          return CompletionStatus.VERIFIED_SUCCESS.value, True
  ```
  If `self.checks` is non-empty and all checks passed, `evaluate_status()` immediately returns `VERIFIED SUCCESS`, regardless of whether:
  - `self.task_completed` is `False`.
  - `self.is_paused` is `True`.
  - In `orchestrator.py` and `coordinator.py`, `HonestCompletionReport` is instantiated without passing `task_completed` or `is_paused`, defaulting them to `True` and `False` respectively.
* **Impact:** Any task that fails or pauses while executing a test check that passes will be crowned `VERIFIED SUCCESS`.

---

### Defect 2: Conflation of System Health vs. User Task Verification
* **Source Locations:**
  - [`src/codemind/verification/runner.py#L30-L75`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/verification/runner.py#L30-L75)
  - [`src/codemind/runtime/agent.py#L294-L300`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/runtime/agent.py#L294-L300)
  - [`src/codemind/orchestration/orchestrator.py#L298-L305`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/orchestration/orchestrator.py#L298-L305)
* **Root Cause Mechanism:**
  The verification runner uses a generic heuristic `discover_test_command()` that checks the workspace root for testing infrastructure:
  ```python
  if (workspace_root / "run_tests.py").is_file():
      return "python3 run_tests.py"
  ```
  When a developer runs CodeMind within the `CodeMind-CLI` repository (or any repository containing its own test suite), CodeMind executes **its own regression tests** (`run_tests.py`) and evaluates the outcome as verification of the user's task.
* **Impact:** If the user asks CodeMind to build a React portfolio in `documents/portfolio`, CodeMind tests its own Python agent codebase instead of the user's React deliverable.

---

### Defect 3: File Attribution Contamination Across Tasks
* **Source Locations:**
  - [`src/codemind/runtime/agent.py#L233-L235`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/runtime/agent.py#L233-L235)
  - [`src/codemind/runtime/agent.py#L350-L353`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/runtime/agent.py#L350-L353)
  - [`src/codemind/orchestration/orchestrator.py#L214-L216`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/orchestration/orchestrator.py#L214-L216)
* **Root Cause Mechanism:**
  1. In `agent.py`, `self.active_snapshot.files_changed` is a global session-level accumulator:
     ```python
     self.active_snapshot.files_changed = list(
         set(self.active_snapshot.files_changed + final_state.files_created + final_state.files_modified)
     )
     ```
     When subsequent tasks execute in the same interactive session (e.g. Task 1: Flappy Bird, Task 2: Instagram, Task 3: Portfolio), `self.active_snapshot.files_changed` retains files from all prior tasks.
  2. In `orchestrator.py`, if a checkpoint exists from a previous incomplete run, `self.files_created` is loaded indiscriminately from `latest.files_created`, injecting old file paths into the new task's report.
* **Impact:** Every subsequent task report becomes bloated with stale, unrelated files created in prior sessions.

---

### Defect 4: Malformed Response Loop and Unbounded Turn Consumption
* **Source Locations:**
  - [`src/codemind/runtime/loop.py#L241-L260`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/runtime/loop.py#L241-L260)
  - [`src/codemind/models/protocol.py#L65-L120`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/models/protocol.py#L65-L120)
  - [`src/codemind/models/normalizer.py#L20-L80`](file:///Users/dev/Documents/cli/CodeMind-CLI/src/codemind/models/normalizer.py#L20-L80)
* **Root Cause Mechanism:**
  1. The protocol parser strictly demands clean JSON. When local models output natural language preambles, unescaped quotes, or conversational explanations around tool calls, the parser yields `MalformedAction`.
  2. In `loop.py`, `MalformedAction` loopback messages are counted as **full execution turns**:
     - Turn 1: Malformed response -> loopback feedback.
     - Turn 2: Malformed response -> loopback feedback.
     - Turn 3: Malformed response -> loopback feedback.
  3. If the model oscillates between malformed envelopes and partial plans, 10–15 turns are consumed purely on syntactic error corrections.
  4. The 20-turn limit is hit before the model performs meaningful file mutations.
* **Impact:** Turn exhaustion occurs rapidly without progress, leaving the task aborted or stranded in a paused state.

---

## 3. Summary of Architectural Violations

| Observed Symptom | Underlying Architecture Defect | Remediation Target |
|---|---|---|
| `VERIFIED SUCCESS` printed on paused task | Flawed conditional precedence in `HonestCompletionReport.evaluate_status()` | Workstream C: Invariant enforcement |
| CodeMind internal tests run for user tasks | `discover_test_command()` lacks target scope isolation | Workstream C: User acceptance separation |
| `insta_gram` / `flappy_bird` files in report | Session-level mutable list pollution and checkpoint contamination | Workstream B: Task-scoped `FileChangeLedger` |
| 20 turns exhausted on format errors | Protocol repair counted as execution turns; insufficient pre-parse normalization | Workstream A: Dedicated Protocol Pipeline |
