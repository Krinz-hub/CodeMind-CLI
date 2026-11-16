# CodeMind Phase 8 — Agent Runtime Reliability & Lifecycle Guarantees

**Document:** `PHASE_8_RUNTIME_RELIABILITY.md`  
**Author:** AI Agent-Runtime Systems Engineer  
**Date:** 2026-11-16  
**Status:** Complete  

---

## 1. Core Runtime Lifecycle Architecture

CodeMind tasks transition through a formal finite state machine (FSM):

```text
       [ Start / New Task ]
                │
                ▼
        ┌───────────────┐
        │   PLANNING    │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │   EXECUTING   │◀──────────────┐
        └───────┬───────┘               │
                │                       │
      ┌─────────┴──────────┐            │ continue / resume
      ▼                    ▼            │
┌───────────┐        ┌───────────┐      │
│  PAUSED   │        │ CANCELLED │      │
│(Turn/Tool)│        │ (Ctrl+C)  │      │
└─────┬─────┘        └─────┬─────┘      │
      │                    │            │
      └────────────────────┴────────────┘
                │
                ▼ (All steps done + files on disk)
        ┌───────────────┐
        │   TESTING /   │
        │ VERIFICATION  │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │   COMPLETED   │
        └───────────────┘
```

---

## 2. Technical Invariants & Reliability Mechanisms

### 2.1 Turn-Budget Segment Isolation
- **Invariant:** A task segment's turn counter `state.turn_count` MUST ALWAYS start at `0`.
- **Session vs. Task Separation:** Cumulative session turns are tracked in `SessionSnapshot.turns_completed`. The per-task loop budget is governed strictly by `AgentState.turn_count` compared against `max_turns`.
- **No REPL Leak:** Starting a new task instruction resets `turn_count = 0` and clears `files_created = []`, completely preventing the bug where earlier tasks blocked subsequent inputs.

### 2.2 Clean Turn Exhaustion Handling
When `current_turn >= max_turns`:
1. Loop terminates without throwing exceptions.
2. `state.is_paused = True`, `state.status = "paused"`.
3. In-flight tasks in `state.plan` are marked as `TaskStatus.PAUSED`.
4. Event `AgentEventType.TASK_PAUSED` is emitted.
5. An atomic `WorkflowCheckpoint` is serialized and saved via `CheckpointManager.save_checkpoint_atomic()`.
6. `HonestCompletionReport` records `CompletionStatus.PAUSED` and withholds verification success.

### 2.3 Resumption via `continue` / `resume`
When the user types `continue` or invokes `codemind resume`:
1. The agent inspects `active_snapshot` and loads the latest checkpoint.
2. Prior conversation history and completed subtasks are preserved.
3. Paused subtasks are restored to `pending`.
4. A fresh turn budget is allocated (`turn_count = 0`).
5. A structured continuation directive is passed to the agent runtime, enabling execution to pick up exactly where it was suspended.

### 2.4 Ground-Truth Disk Verification
In `HonestCompletionReport.evaluate_status(workspace_root)`:
```python
if workspace_root:
    for rel_path in self.files_created:
        full_path = workspace_root / rel_path
        if not full_path.is_file() and not full_path.is_dir():
            missing_files.append(rel_path)

if missing_files:
    return CompletionStatus.FAILED, f"FAILED (Missing expected files: {', '.join(missing_files)})"
```
Even if unit tests pass, if an artifact claimed in `files_created` is absent from disk, the report immediately flips to `FAILED`.

### 2.5 Two-Stage Ctrl+C Cancellation
In `src/codemind/cli/main.py` and `AgentLoop`:
1. **First `SIGINT` (Ctrl+C):**
   - Intercepted by `_current_loop.cancel()`.
   - The active tool or model request is safely aborted.
   - Task is transitioned to `CANCELLED` and `PAUSED`.
   - Atomic workflow checkpoint is saved.
   - The user is notified and returned to the REPL prompt without process termination.
2. **Second `SIGINT` (within 2 seconds):**
   - Gracefully terminates the REPL process.

---

## 3. YouTube Clone (`documents/yt`) Audit & Integrity Report

### 3.1 Workspace Inspection Findings
- Target Directory: `documents/yt`
- `index.html`: Contains full DOM markup for video feed, sidebar, and navbar. Line 150 explicitly includes:
  ```html
  <script src="script.js"></script>
  ```
- `style.css`: Complete styling for player container, grid layout, and dark theme.
- `script.js`: **Missing from disk.**

### 3.2 Integrity Stance
In accordance with user directives:
- The missing `script.js` was NOT automatically hallucinated or silently injected.
- The previous false completion claim was audited and flagged as a test leak artifact.
- The YouTube clone workflow remains in `documents/yt` awaiting explicit user resumption (`codemind resume` or interactive prompt).

---
