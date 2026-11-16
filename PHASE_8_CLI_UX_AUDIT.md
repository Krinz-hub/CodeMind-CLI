# CodeMind Phase 8 — Critical CLI UX & Runtime Reliability Audit

**Document:** `PHASE_8_CLI_UX_AUDIT.md`  
**Author:** Principal Terminal UI & AI Agent-Runtime Engineer  
**Date:** 2026-11-16  
**Status:** Complete  

---

## 1. Executive Summary

During real-world dogfooding and benchmark evaluations, CodeMind demonstrated robust low-level capabilities (tool execution, skills discovery, persistent memory, and multi-agent coordination). However, its user-facing CLI and runtime lifecycle suffered from critical defects that degraded the user experience into that of an unpolished, fragile REPL.

Specifically, five severe reliability and usability bugs were discovered:
1. **Turn-Budget Leak Across REPL Tasks:** Entering a new instruction after an earlier task exhausted its turn limit immediately failed without executing any turns.
2. **False `VERIFIED SUCCESS` Claims:** Incomplete or paused workflows were stamped as verified successes if workspace unit tests happened to pass, even when core implementation steps were never executed.
3. **Ghost Artifact Verification in `documents/yt`:** The YouTube clone task in `documents/yt` reached turn limit at turn 20 without creating `script.js`, yet was reported as successful.
4. **Crude TUI & Raw Dictionary Dumps:** The CLI dumped raw Python dictionaries to `stdout`, lacked structured plan progress visualization, and offered no turn/token gauges.
5. **Brittle Signal Handling & Session Corruption:** Pressing `Ctrl+C` caused unhandled Python traceback exceptions, failed to persist workflow checkpoints, and left the REPL in an inconsistent state.

This document provides a root-cause forensic audit of these defects.

---

## 2. Forensic Analysis of Identified Failure Modes

### 2.1 The Turn-Budget REPL Leak

#### Root Cause
In `src/codemind/runtime/agent.py` prior to the upgrade:
```python
# PREVIOUS BUGGY CODE IN run_task:
state = AgentState(
    session_id=self.active_snapshot.session_id,
    workspace_root=str(self.workspace_root),
    task_instruction=instruction,
    turn_count=self.active_snapshot.turns_completed,  # BUG: cumulative session turns assigned to task turn_count
    files_created=list(self.active_snapshot.files_changed),  # BUG: prior task files leaked into new task
    files_modified=[],
    messages=messages,
)
```
When `active_snapshot.turns_completed` reached or exceeded `max_turns` (e.g., 20/20), any subsequent task initiated in the same session was initialized with `turn_count = 20`. In `AgentLoop.execute_task`:
```python
if state.turn_count >= self.max_turns:
    break
```
Because `20 >= 20` was evaluated immediately on turn 0, the agent loop terminated without prompting the model or executing a single tool call, returning:
`"Turn limit reached (20 turns). Halting."`

#### Impact
Users were forced to kill the CLI process and restart from scratch whenever any single task reached its turn limit.

---

### 2.2 False Verification & Stale Artifact Leaks

#### Root Cause
In `src/codemind/verification/reporter.py`:
1. `HonestCompletionReport.verified` evaluated purely whether any test check passed (`all(c.passed for c in self.checks)`), completely ignoring whether the task was actually completed, paused, cancelled, or whether created files existed on disk.
2. If no test checks were run, it defaulted to `task_completed`.
3. In `agent.py`, `state.files_created` was seeded with `self.active_snapshot.files_changed`. If Task 1 created `foo.py` and Task 2 was run, Task 2's report claimed `foo.py` was created by Task 2.
4. Crucially, neither the loop nor the reporter verified that files claimed in `files_created` actually existed on disk at completion time.

#### Impact
If the model generated a JSON response claiming a file was created or if a test suite passed prior to implementation, CodeMind falsely celebrated `VERIFIED SUCCESS`.

---

### 2.3 The `documents/yt` YouTube Clone Incomplete Workflow

#### Forensic Examination of `documents/yt`
Inspection of the directory revealed:
- `index.html` (6,071 bytes): references `<script src="script.js"></script>` at line 150.
- `style.css` (3,743 bytes): fully styled dark-theme YouTube layout.
- `script.js`: **DOES NOT EXIST ON DISK**.

#### Trajectory Replay
The evaluation trajectory of the YouTube clone task showed:
1. Turn 1: Inspect repository directory.
2. Turn 2: Generate `index.html`.
3. Turn 3: Generate `style.css`.
4. Turn 4–20: Iterative adjustments to CSS and inspection of mock data.
5. Turn 20: Hit `max_turns=20`. Halting triggered.
6. Report generation: Due to the verification leak, the session was marked as complete, and the completion report did not inspect disk presence of `script.js`.

The user was misled to believe the YouTube clone was functional, but opening `index.html` resulted in broken interactive controls (search, filter chips, video modal playback) due to the missing script.

---

### 2.4 Unpolished Terminal UI & Raw Python Dict Dumps

#### Observed Experience
- Tool calls were rendered as:
  ```python
  {'tool': 'write_file', 'arguments': {'path': 'main.py', 'content': 'def run():\n    pass'}, 'reason': 'initial setup'}
  ```
- No visual indicators for turn budget or token usage.
- Task plans were either omitted or printed as unformatted strings.
- Approvals in `supervised` mode used basic `input("Approve? (y/n): ")` without clear context, parameter visibility, or risk highlighting.

---

### 2.5 Brittle Interrupt Handling (`Ctrl+C`)

#### Observed Experience
When a user pressed `Ctrl+C` during tool execution or LLM streaming:
```
^CTraceback (most recent call last):
  File "src/codemind/cli/main.py", line 124, in repl
    asyncio.run(agent.run_task(cmd))
  ...
KeyboardInterrupt
```
- No checkpoint was saved.
- File handles and temp files remained unfinalized.
- The entire process crashed back to the shell, losing all session progress.

---

## 3. Remediation Matrix

| Defect | Severity | Root Cause | Target Architectural Solution |
| :--- | :--- | :--- | :--- |
| **Turn Budget Leak** | Critical | Cumulative turns assigned to per-task turn counter | Decouple task turn counter (`turn_count = 0` per segment) from session cumulative turns. Introduce explicit `TaskStatus.PAUSED`. |
| **False Verification** | Critical | Reporter ignored task status and disk state | Add `evaluate_status(workspace_root)` with strict disk file existence check; pause/cancelled status disallows `VERIFIED_SUCCESS`. |
| **Missing `script.js`** | High | Silent turn exhaustion in `documents/yt` | Enforce honest reporting. Resumption must be explicit via `continue`/`resume`. |
| **Raw Dict Dumps** | Medium | Direct `print(action.dict())` in UI | Build `CodeMindTUI` using Rich with dark theme (`#1A1B26`), parameter cards, and progress meters. |
| **Ctrl+C Crash** | High | Raw `KeyboardInterrupt` unhandled in REPL loop | Two-stage SIGINT handler: 1st Ctrl+C gracefully pauses task and saves atomic checkpoint; 2nd Ctrl+C exits REPL. |

---
