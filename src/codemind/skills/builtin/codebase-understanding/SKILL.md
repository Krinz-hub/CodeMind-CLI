---
name: codebase-understanding
version: 1.0.0
description: Exploration strategy for unfamiliar repositories, architecture mapping, entry point discovery, and dependency tracing.
category: workflow
triggers:
  manifests:
    - "README.md"
    - "ARCHITECTURE.md"
  globs: []
  keywords:
    - "understand"
    - "explore"
    - "architecture"
    - "overview"
    - "structure"
    - "explain"
    - "entry point"
    - "inspect codebase"
required_tools:
  - read_file
  - list_directory
  - file_search
dependencies: []
conflicts: []
workflow_steps:
  - "1. Scan packaging manifests (pyproject.toml, package.json, Cargo.toml, go.mod) to identify primary language, frameworks, and tools."
  - "2. Locate documentation (README.md, docs/) to understand project domain, business purpose, and high-level architecture."
  - "3. Identify execution entry points (main.py, index.ts, app.py, cli.py) and map data flow through the system."
  - "4. Inspect directory layout up to depth 2 to understand module boundaries and separation of concerns."
  - "5. Locate and analyze test directories to observe how the codebase is exercised and verified."
  - "6. Formulate a structured architectural summary covering purpose, tech stack, key components, and operational commands."
constraints:
  - "Do not read every individual file sequentially; perform targeted top-down inspection starting from manifests."
  - "Avoid modifying any repository files during a pure understanding or exploration query."
  - "Ground all architectural assertions strictly on observed manifests and source code; never speculate on framework usage."
verification:
  - "Produce a factual, evidence-backed architectural summary citing verified files and entry points."
enabled: true
---

# Codebase Understanding & Exploration Strategy

## 1. Top-Down Reconnaissance
1. **Packaging Manifests:** What is the technology stack? Read `pyproject.toml`, `package.json`, etc.
2. **Operational Commands:** How is the project run, tested, and linted?
3. **Primary Entry Points:** Trace from the main entry point down into routers/controllers.
4. **Data Models & Stores:** Where is state persisted? Trace database schemas or ORM models.

## 2. Structured Architectural Report Template
- **Project Domain & Purpose:** High-level problem being solved.
- **Technology Stack:** Languages, frameworks, and runtime versions.
- **Key Modules & Responsibilities:** Directory layout and component boundaries.
- **Entry Points & Execution Flow:** How requests or commands enter and travel through the system.
- **Test & Verification Commands:** Commands to run automated tests.
