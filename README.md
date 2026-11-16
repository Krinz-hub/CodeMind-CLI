# ▟●▙ CodeMind CLI

> **Your local AI engineering companion.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Local First](https://img.shields.io/badge/architecture-local--first-green.svg)](#architecture)

CodeMind CLI is a local-first, modular autonomous coding agent that provides local and compatible AI models with a structured, verified, and sandboxed environment to perform real software engineering tasks.

---

## Key Capabilities

- **Local-First & Model-Agnostic:** Built from the ground up to operate with local LLM endpoints (CodeMind local runtime, Ollama, vLLM, llama.cpp, or OpenAI-compatible local servers) without mandatory cloud dependencies.
- **Controlled Agent Loop:** Bounded execution loop with explicit turn limits, output limits, and timeouts. Prevents runaway tool execution.
- **Strict Least-Privilege Security:** Workspace path enforcement (symlink and traversal checks), automated redaction of sensitive credentials, and mandatory human approval gates for write/execute actions.
- **Structured Task Planning:** Authors and updates structured task DAGs (Pending, In Progress, Blocked, Completed, Failed, Skipped) rather than ephemeral conversational promises.
- **Honest Verification Engine:** Distinguishes between generated code, actual file modifications, and real test execution. Never claims a build succeeded unless verification was actively executed.
- **Recoverable Sessions & Memory:** Persists task state, tool events, and conversations for seamless session resumption and post-mortem evaluation traces.

---

## One-Command Global Installation

CodeMind includes a zero-configuration global launcher that automatically locates and manages its dedicated virtual environment without requiring manual activation:

```bash
# Clone and run one-command installer
cd "codemind cli"
./install.sh
```

Or install via Python packaging:
```bash
pip install -e .
```

To verify full system, environment, and inference model health:
```bash
codemind doctor
```

For detailed setup instructions, troubleshooting, and self-update commands, see [docs/INSTALLATION.md](docs/INSTALLATION.md).

---

## Quickstart

### 1. Interactive Companion Mode
Launch the CodeMind interactive companion (**Milo**) from **any directory**:
```bash
codemind
```

### 2. One-Shot Autonomous Task
Run a direct engineering task or query from anywhere:
```bash
codemind "Refactor auth middleware in src/auth.py and author regression tests"
```

### 3. System & Model Diagnostics
Run comprehensive environment, dependency, and local model checks:
```bash
codemind doctor
```

### 4. Resume Session
Continue an interrupted task or revisit past history:
```bash
codemind --resume <session-id>
```

### 5. Status & Model Inspection
Verify local inference connectivity and active workspace permissions:
```bash
codemind status
codemind models list
```

---

## Architecture Overview

```text
┌──────────────────────────────────────────────┐
│                 CodeMind CLI                 │
│  Input · Streaming · Plans · Approvals · UI   │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│                 Agent Runtime                │
│ Request Router · Agent Loop · Task Manager   │
│ Context Manager · Session Manager            │
│ Permission Manager · Event/Trace Logger      │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│                  Model Layer                 │
│ Model Adapter · Prompt Builder · Parser      │
│ CodeMind Local Adapter · Other Test Adapters │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│                 Tool System                  │
│ Files · Search · Terminal · Git · Tests      │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│            Observation & Verification        │
│ Results · Errors · Diff · Tests · Summary    │
└──────────────────────────────────────────────┘
```

---

## Verification & Testing

Run all unit, integration, and security tests hermetically offline:
```bash
python3 run_tests.py
```
