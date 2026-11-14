# Agent Execution Loop: CodeMind CLI

## 1. Execution Lifecycle

The execution loop is deterministic, observable, and strictly bounded. It prevents infinite model-tool loops and resource exhaustion.

```text
User Request
    │
    ▼
[Step 1: Workspace Normalization]
    Validate workspace root, git context, and active permissions.
    │
    ▼
[Step 2: Context Retrieval]
    Assemble workspace summary, directory tree, recent diffs, and relevant files.
    │
    ▼
[Step 3: Prompt Construction]
    Combine system instructions, tool schemas, task plan, and conversation history.
    │
    ▼
[Step 4: Model Invocation]
    Query configured ModelAdapter (streaming/non-streaming with timeout).
    │
    ▼
[Step 5: Protocol Parsing & Validation]
    Parse JSON envelope. Check protocol_version, action type, tool name, and arguments.
    ├─ If malformed: return structured error feedback to model (max 3 retry attempts).
    │
    ▼
[Step 6: Action Dispatch]
    ├─ If Action == "tool_call":
    │   ├─ Check Security/Permissions (read-only, supervised approval, or trusted).
    │   ├─ If Approval required: prompt user with command/diff preview.
    │   ├─ Execute tool via ToolExecutor with timeout and output truncation.
    │   ├─ Append observation (ToolResult) to session history and plan evidence.
    │   └─ Decrement remaining loop turns. Loop to Step 2 if turns remain.
    │
    ├─ If Action == "plan":
    │   ├─ Update authoritative TaskPlan.
    │   └─ Loop to Step 4 with updated task state.
    │
    └─ If Action == "final":
        ├─ Proceed to Step 7.
        │
    ▼
[Step 7: Verification & Finalization]
    ├─ Check if file modifications were made.
    ├─ If auto-verify enabled: run detected project test runner.
    ├─ Synthesize honest completion report (changed files, test pass/fail/unrun).
    └─ Persist session checkpoint to disk.
```

## 2. Hard Limits & Loop Guards

| Parameter | Default | Config Key | Purpose |
|---|---|---|---|
| `max_turns` | 20 | `runtime.max_turns` | Prevents runaway multi-turn loops. |
| `max_tool_calls` | 30 | `runtime.max_tool_calls` | Bounds total tool invocations per task. |
| `max_output_bytes` | 65,536 (64 KB) | `tools.max_output_bytes` | Prevents context blowing from giant logs/files. |
| `tool_timeout_seconds`| 60 | `tools.timeout_seconds` | Terminate hung commands or frozen processes. |
| `model_timeout_seconds`| 120 | `model.timeout_seconds` | Guard against hung model serving inferences. |

## 3. Protocol Envelope Specification (v1)

### Tool Call Envelope
```json
{
  "protocol_version": "1",
  "type": "tool_call",
  "tool": "read_file",
  "arguments": {
    "path": "src/main.py"
  },
  "reason": "Examine the application entry point to locate the router."
}
```

### Plan Update Envelope
```json
{
  "protocol_version": "1",
  "type": "plan",
  "plan": [
    {"id": "task-1", "title": "Inspect database models", "status": "completed"},
    {"id": "task-2", "title": "Add auth routes", "status": "in_progress"},
    {"id": "task-3", "title": "Run test suite", "status": "pending"}
  ],
  "reason": "Updated plan based on inspected schemas."
}
```

### Final Response Envelope
```json
{
  "protocol_version": "1",
  "type": "final",
  "content": "Added authentication middleware and validated existing endpoints.",
  "summary": [
    "Created src/auth.py with JWT verification",
    "Mounted auth middleware in src/app.py",
    "Verified tests passing"
  ]
}
```
