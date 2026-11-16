---
name: python-backend
version: 1.0.0
description: Idiomatic Python backend engineering with clean architecture, typing, and robust error handling.
category: backend
triggers:
  manifests:
    - "pyproject.toml"
    - "setup.py"
    - "requirements.txt"
    - "Pipfile"
  globs:
    - "*.py"
  keywords:
    - "python"
    - "backend"
    - "fastapi"
    - "flask"
    - "django"
    - "service"
    - "router"
    - "pydantic"
required_tools:
  - read_file
  - create_file
  - apply_patch
  - run_command
dependencies: []
conflicts: []
workflow_steps:
  - "1. Inspect existing manifests (pyproject.toml, requirements.txt) and entry points to understand dependencies and architecture."
  - "2. Define clear function and class interfaces with Python 3.10+ typing annotations."
  - "3. Implement modular domain services, keeping business logic distinct from HTTP transport layers."
  - "4. Ensure explicit exception hierarchies; eliminate bare except blocks and handle partial failures gracefully."
  - "5. Add automated unit and integration tests, then verify execution with the project test runner."
constraints:
  - "Always include type annotations on function parameters and returns."
  - "Use `from __future__ import annotations` when using modern union types (int | None)."
  - "Never catch generic `Exception` without re-raising or logging detailed diagnostic context."
  - "Do not introduce external dependencies without checking existing packaging manifests."
verification:
  - "Run the project test suite (pytest or unittest) and confirm 100% pass rate."
enabled: true
---

# Python Backend Engineering Workflow

## 1. Architectural Principles
- **Separation of Concerns:** Separate data access, business domain rules, and transport controllers (FastAPI routers, CLI endpoints).
- **Explicit Typing:** Leverage Python 3.10+ type annotations (`int | None`, `dict[str, Any]`, `Callable`).
- **Defensive Error Handling:** Author domain-specific exception classes inheriting from standard Python base exceptions.

## 2. Step-by-Step Implementation Protocol
1. **Reconnaissance:** Inspect `pyproject.toml` or `setup.py` to identify active frameworks (FastAPI, Flask, Django, etc.).
2. **Interface First:** Draft function signatures, dataclasses, or Pydantic models before writing business logic.
3. **Targeted Patching:** Use `apply_patch` for minimal edits. Avoid rewriting entire modules when adding or modifying functions.
4. **Hermetic Verification:** Run project test runners with `PYTHONPATH=src:.` to verify functional correctness.
