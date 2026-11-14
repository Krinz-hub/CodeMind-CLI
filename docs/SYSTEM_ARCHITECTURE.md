# System Architecture: CodeMind CLI

## 1. High-Level Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────┐
│                       CLI Interface                         │
│   Terminal Renderer (Rich) · Command Parser · User Prompt   │
│   Diff Viewer · Plan Visualizer · Approval Prompts          │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                       Agent Runtime                         │
│  ┌────────────────────────┐     ┌────────────────────────┐  │
│  │   Request Orchestrator │     │   Bounded Agent Loop   │  │
│  └───────────┬────────────┘     └───────────┬────────────┘  │
│              │                              │               │
│  ┌───────────▼────────────┐     ┌───────────▼────────────┐  │
│  │     Task Planner       │     │    Context Manager     │  │
│  │  (State DAG & Updates) │     │ (Budget & Relevance)   │  │
│  └────────────────────────┘     └────────────────────────┘  │
│              │                              │               │
│  ┌───────────▼────────────┐     ┌───────────▼────────────┐  │
│  │     Session Engine     │     │   Trace/Event Logger   │  │
│  │ (Checkpoints & Resume) │     │ (Redacted Audit Trail) │  │
│  └────────────────────────┘     └────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────┘
                               │
       ┌───────────────────────┼───────────────────────┐
       │                       │                       │
┌──────▼──────┐         ┌──────▼──────┐         ┌──────▼──────┐
│ Model Layer │         │ Tool System │         │  Security   │
│ ModelAdapter│         │ Registry    │         │ Permissions │
│ Protocol v1 │         │ Files/Search│         │ Sandbox/Path│
│ CodeMind/Oll│         │ Term/Patch  │         │ Redaction   │
└─────────────┘         └─────────────┘         └─────────────┘
                               │
                        ┌──────▼──────┐
                        │Verification │
                        │Runner/Checks│
                        └─────────────┘
```

## 2. Core Subsystems

### 2.1 CLI Presentation Subsystem (`codemind.cli`)
- Built on `rich` and `typer`.
- Renders progress indicators, markdown explanations, syntax-highlighted diffs, and formatted task tables.
- Supports plain mode (no ANSI/colors) for minimal terminals and screen readers.

### 2.2 Agent Runtime Subsystem (`codemind.runtime`)
- Orchestrates multi-turn task execution.
- Implements strict turn limits, token ceilings, output truncations, and cancellation handling.
- Translates model intent into structured actions via the v1 envelope.

### 2.3 Model Layer (`codemind.models`)
- `ModelAdapter` abstract protocol.
- `CodeMindLocalAdapter`: Standard OpenAI-compatible local server client.
- `OllamaAdapter`: Direct Ollama API client.
- `MockModelAdapter`: Fully offline deterministic adapter for automated testing.
- `ProtocolParser`: Extracts and validates JSON envelopes from model responses with schema validation and error feedback loops.

### 2.4 Tool Subsystem (`codemind.tools`)
- Strictly typed input schemas (via Pydantic).
- Unified `ToolResult` interface capturing status, outputs, exit codes, and truncation metadata.
- Core tools: `read_file`, `list_directory`, `search_files`, `search_text`, `create_file`, `apply_patch`, `run_command`, `git_status`, `git_diff`.

### 2.5 Security Subsystem (`codemind.security`)
- Workspace sandboxing with absolute canonical path resolution preventing path traversal (`../`) and symlink attacks.
- Policy enforcement: `read-only`, `supervised`, `trusted`.
- Secret scanner and redactor for `.env`, API keys, certificates, and private keys.

### 2.6 Task Planning Subsystem (`codemind.planning`)
- Maintains authoritative task DAGs (Pending, In Progress, Blocked, Completed, Failed, Skipped).
- Tracks prerequisites, target files, and tangible evidence for every step.

### 2.7 Verification Subsystem (`codemind.verification`)
- Discovers project-specific test runners (`pytest`, `unittest`, `npm test`, `cargo test`, `make test`).
- Executes verification runs with timeouts.
- Produces honest reports distinguishing executed tests from unverified changes.

### 2.8 Session & Memory Subsystem (`codemind.sessions`, `codemind.memory`)
- JSON-backed local persistence stored inside `.codemind/sessions/`.
- Enables full session resumption, state rehydration, and task continuation.
