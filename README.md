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

## Installation

```bash
cd "codemind cli"
pip install -e .
```

---

## Quickstart

### 1. Interactive Mode
Launch the CodeMind companion interactive terminal:
```bash
codemind
```

### 2. One-Shot Task
Run a direct query or task:
```bash
codemind "Explain the structure and entrypoints of this project"
```

### 3. Resume Session
Continue an interrupted task or revisit past history:
```bash
codemind --resume <session-id>
```

### 4. Configuration Check
Verify local inference connectivity and active workspace permissions:
```bash
codemind status
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
