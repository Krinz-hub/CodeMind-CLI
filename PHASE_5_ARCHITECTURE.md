# CodeMind Phase 5 — Dynamic Skills Discovery and Execution Engine Architecture

**Document Version:** 1.0.0  
**Status:** Approved Architecture Specification  
**Author:** Principal AI Agent Architect & Senior Software Engineer  
**Date:** 2026-11-16  
**System Target:** CodeMind CLI (Local-First Engineering Companion)

---

## 1. Executive Summary & Objective

In Phases 1 through 4, CodeMind CLI established:
1. A bounded, self-correcting agent execution loop (`AgentLoop`).
2. Local model adapters with capabilities testing (`qwen3.6:35b`, `OllamaAdapter`).
3. Empirical agent evaluation across real-world engineering tasks (Phase 3).
4. Persistent, local-first 4-tier project memory with SQLite FTS5 (Phase 4).

However, up to this point, specialized engineering procedures—such as building React components, structuring FastAPI routers, designing database migrations, or executing systematic debugging—relied either on the model's generic pretraining or on primitive string matching in a rudimentary skill loader.

**Phase 5 introduces the Dynamic Skills Discovery, Selection, and Execution Engine.** Its objective is to allow CodeMind to discover, understand, select, and execute specialized, versioned engineering workflows dynamically without hardcoding procedural logic into the agent core or expanding model weights.

---

## 2. Conceptual Definition: What is a Skill?

A **Skill** in CodeMind is a versioned, self-contained, human-readable package that guides the agent through a domain-specific engineering task. A skill contains:
- **Identity & Metadata:** Unique name, version, category, description, and author.
- **Triggers:** Declarative activation criteria based on project manifests (e.g., `package.json`, `pyproject.toml`), file extensions, or user task intent keywords.
- **Workflows & Procedures:** Step-by-step phased instructions detailing how to approach the task.
- **Constraints & Best Practices:** Explicit negative and positive boundaries (e.g. "Do not introduce third-party libraries without checking package manifest").
- **Verification Criteria:** Actionable instructions on how to prove the work succeeded (e.g., test commands, lint checks).
- **Tool Requirements:** Declarative inventory of tools required (`read_file`, `apply_patch`, `run_command`).
- **Relationships:** Dependencies on other skills and conflict declarations.

> [!IMPORTANT]
> **The Untrusted Skill Principle:** Skills provide *instructions*, not *permissions*. A skill cannot grant permission bypasses, override workspace sandbox boundaries, disable human-in-the-loop terminal confirmations, or execute arbitrary shell scripts merely by being discovered. All tool operations remain strictly subject to CodeMind's `WorkspaceSandbox` and `PermissionChecker`.

---

## 3. Skill Specification & Format

### 3.1 `SKILL.md` File Structure
Every skill is stored in its own directory containing a canonical `SKILL.md` file. It features structured YAML frontmatter followed by standard markdown instructions:

```markdown
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
required_tools:
  - read_file
  - create_file
  - apply_patch
  - run_command
dependencies: []
conflicts: []
workflow_steps:
  - "1. Inspect existing project structure and packaging configuration."
  - "2. Define clear type signatures using Python 3.10+ typing standards."
  - "3. Implement modular service/domain logic separated from transports."
  - "4. Ensure explicit exception hierarchies; eliminate bare except blocks."
  - "5. Add automated unit/integration tests and verify with project runner."
constraints:
  - "Always include type annotations for all public function parameters and returns."
  - "Use `from __future__ import annotations` when using modern union types."
  - "Do not introduce new third-party dependencies without verifying existing manifests."
verification:
  - "Execute project test suite (pytest or unittest) and confirm all checks pass."
enabled: true
---

# Python Backend Engineering Workflow

## Detailed Execution Guidelines
...
```

### 3.2 Manifest Schema Validation
Before a skill is loaded into memory, its frontmatter is validated against a strict schema (`SkillManifest` model):
- Required: `name`, `version`, `description`, `category`.
- Format: `name` must match `^[a-z0-9]+(-[a-z0-9]+)*$` (kebab-case).
- Version: Valid SemVer string (`X.Y.Z`).
- Sanitization: Incompatible, malformed, or hostile frontmatter is flagged, quarantined, and reported without crashing the runtime.

---

## 4. Multi-Tier Skill Discovery

Skills are discovered hierarchically across three distinct filesystem locations:

```
+-------------------------------------------------------------------------+
|                        Skill Discovery Engine                           |
+-------------------------------------------------------------------------+
  1. Built-in Skills:     <codemind_install>/skills/builtin/*/SKILL.md
  2. User-level Skills:   ~/.codemind/skills/*/SKILL.md
  3. Project-level Skills: <workspace_root>/.codemind/skills/*/SKILL.md
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                  Conflict & Precedence Resolution                       |
|   Rule: Project-Level > User-Level > Built-In (Identical Skill Name)    |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                      Active Skill Registry (Validated)                  |
+-------------------------------------------------------------------------+
```

### Discovery Rules
1. **Hierarchical Overrides:** A project-level skill with `name: python-backend` completely overrides a user-level or built-in skill of the same name.
2. **Explicit Enable/Disable States:** Skills can be enabled or disabled globally or per-workspace via `.codemind/skills_config.json`.
3. **Lazy Reading:** Discovery scans metadata (YAML frontmatter) first; full instruction markdown bodies are only read when a skill is actively selected.

---

## 5. Intelligent Skill Selection Pipeline

The agent coordinates a 2-stage selection pipeline to prevent context bloat:

```
[User Task Instruction + Project Summary + Memory Layer A]
                           |
                           v
               +-----------------------+
               |  Stage 1: Pre-Filter  |
               +-----------------------+
               | • Manifest matching   |
               | • Keyword intent match|
               | • Memory consistency  |
               +-----------------------+
                           |
                     (Top 3-5 Candidates)
                           |
                           v
               +-----------------------+
               |  Stage 2: Selection   |
               +-----------------------+
               | • Model selects skill |
               | • Explains rationale  |
               | • Resolves deps       |
               | • Resolves conflicts  |
               +-----------------------+
                           |
                     (Selected Skills)
                           |
                           v
               +-----------------------+
               |  Token Budget Check   |
               |  (Max ~4,000-6,000 c) |
               +-----------------------+
                           |
                           v
          [System Prompt Context Injection]
```

### 5.1 Stage 1: Metadata Pre-Filtering
- Checks project manifests (e.g. `package.json` activates frontend skills, `pyproject.toml` activates Python skills).
- Checks intent keywords against the user task prompt (e.g. "debug", "test", "endpoint", "component").
- Cross-references with Layer A project memory to avoid recommending stacks not used by the repository.

### 5.2 Stage 2: Selection, Dependencies & Conflicts
- The agent selects from candidate skills and generates an internal structured selection explanation (e.g., *"Selected `python-backend` and `api-development` because user is adding a REST endpoint"*).
- **Dependency Resolution:** If `api-development` declares a dependency on `python-backend`, both are staged.
- **Conflict Handling:** If two selected skills conflict (e.g. `react-frontend` vs `vue-frontend`), the engine retains the skill that matches project manifests or memory Layer A, suppressing the conflicting alternative.
- **Null Match Fallback:** When no skills match (e.g., "Summarize the commit log"), the agent proceeds cleanly without hallucinating or forcing an irrelevant skill.

---

## 6. Controlled Skill Execution Lifecycle

Every task follows a strict 8-step lifecycle:

$$\text{DISCOVER} \longrightarrow \text{FILTER} \longrightarrow \text{SELECT} \longrightarrow \text{LOAD} \longrightarrow \text{PLAN} \longrightarrow \text{EXECUTE} \longrightarrow \text{VERIFY} \longrightarrow \text{REPORT}$$

1. **DISCOVER:** Scan built-in, user, and project directories.
2. **FILTER:** Score skills based on manifests, files, and keywords.
3. **SELECT:** Select applicable skills; resolve dependencies and conflicts.
4. **LOAD:** Read full instructions and format within the token budget.
5. **PLAN:** The agent formulates a `TaskPlan` incorporating the skill's `workflow_steps`.
6. **EXECUTE:** The agent executes tool calls adhering to the skill's `constraints`.
7. **VERIFY:** The agent runs the skill's `verification` requirements via `VerificationRunner`.
8. **REPORT:** The agent emits a completion summary; unverified work is flagged.

---

## 7. Context Integration & Budgeting

- Memory text and skills text share a disciplined context budget in `ContextBudget`:
  - **Persistent Project Memory:** ~6,000 chars
  - **Active Skills & Guidelines:** ~5,000 chars
  - **Tool Definitions & Protocol:** ~6,000 chars
- If multiple skills are active, instructions are compacted:
  - Workflow steps and constraints are prioritized.
  - Verbose secondary narrative is truncated if approaching the character limit.
- Project memory always grounds skill instructions: for example, if a skill suggests `pytest`, but Project Memory Layer A specifies `python3 -m unittest discover -s tests`, project memory remains authoritative.

---

## 8. CLI Management Suite

Integrated under `codemind skills`:

| Command | Description |
| :--- | :--- |
| `codemind skills list` | Lists all discovered skills, source location, version, and status. |
| `codemind skills show <name>` | Displays detailed workflow steps, constraints, and instructions. |
| `codemind skills search <query>`| Searches skills by name, description, category, and keywords. |
| `codemind skills validate` | Scans all skill folders and reports schema validation errors. |
| `codemind skills enable <name>` | Enables a skill for the workspace. |
| `codemind skills disable <name>`| Disables a skill for the workspace. |
| `codemind skills inspect <name>`| Deep inspection of dependencies, conflicts, and required tools. |

---

## 9. Initial Starter Skill Library

Ten comprehensive built-in skills located in `src/codemind/skills/builtin/`:

1. `python-backend`: Clean architecture, PEP 8, type hints, explicit exceptions, unit tests.
2. `react-frontend`: Functional components, hooks, props typing, state management, accessibility.
3. `react-native-expo`: Mobile UI layout, Expo SDK integrations, navigation, cross-platform performance.
4. `api-development`: REST/GraphQL patterns, idempotency, HTTP status codes, error schemas, payload validation.
5. `database-engineering`: Schemas, migrations, indexing, constraints, query optimization, connection safety.
6. `debugging`: Scientific root-cause reproduction, minimal diff patching, regression testing.
7. `testing`: Hermetic unit tests, mock isolation, edge case coverage, deterministic test runs.
8. `ui-ux-design`: Information hierarchy, visual balance, responsive breakpoints, user feedback states.
9. `git-workflow`: Atomic commits, conventional commit messages, branch hygiene, clean PR prep.
10. `codebase-understanding`: Exploration strategy, architecture mapping, entry point discovery.

---

## 10. Benchmark Evaluation Specification

Thirteen benchmark scenarios in `benchmarks/phase_5/run_phase_5_eval.py`:
- **Scenario A:** Multi-tier skill discovery (built-in, user, project).
- **Scenario B:** Correct skill selection for Python backend task.
- **Scenario C:** Correct skill selection for React frontend task.
- **Scenario D:** Selection of multiple complementary skills (backend + API + testing).
- **Scenario E:** Null matching (no irrelevant skill injected for generic tasks).
- **Scenario F:** Dependency resolution (dependent skill auto-loaded).
- **Scenario G:** Conflicting skill resolution (project preference preserved).
- **Scenario H:** Context budget enforcement (no prompt truncation).
- **Scenario I:** Rejection & isolation of malformed skills.
- **Scenario J:** Resistance to hostile/malicious instructions in untrusted skills.
- **Scenario K:** Strict sandbox permission enforcement during skill execution.
- **Scenario L:** Full lifecycle execution & test verification with active skill.
- **Scenario M:** Project memory integration during skill selection.

---

## 11. Architectural Compliance Matrix

- [x] Model-independent architecture.
- [x] Zero external vector databases, paid APIs, or cloud services.
- [x] Untrusted skill execution model (cannot bypass permissions or sandbox).
- [x] Full backwards compatibility with existing 57 unit & integration tests.
- [x] Structured lifecycle with honest verification reporting.
