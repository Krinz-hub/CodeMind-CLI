# Sessions & Memory: CodeMind CLI

## 1. Local Persistence Architecture

All session transcripts, task state graphs, and tool events are persisted locally under `.codemind/sessions/`.

```text
.codemind/
├── config.toml                     # User / project settings
├── sessions/
│   ├── <session-id>.json           # Complete session snapshot
│   └── <session-id>.events.jsonl   # Append-only chronological trace
└── memory/
    └── project_facts.json          # Scoped project memory (user-editable)
```

---

## 2. Session Schema

Each session snapshot contains:
- `session_id`: Unique timestamped identifier (e.g. `cm-20261114-141520-a1b2`).
- `workspace_root`: Canonical path of the project.
- `created_at` / `updated_at`: ISO 8601 timestamps.
- `model_name` & `provider`: Configured model identifier.
- `permission_mode`: Active security mode (`read-only`, `supervised`, `trusted`).
- `task_plan`: Serialized task DAG with individual statuses and verification artifacts.
- `messages`: Chronological conversation turns and tool observations.
- `statistics`: Total turns, tools invoked, tokens consumed, and files changed.

---

## 3. Resumption & Crash Recovery

The user can resume any prior session via:
```bash
codemind --resume <session-id>
```
During resumption:
1. Workspace root and git state are re-validated.
2. The task plan is restored into the runtime memory.
3. Unfinished tasks remain in `in_progress` or `pending` state with prior observations accessible.
