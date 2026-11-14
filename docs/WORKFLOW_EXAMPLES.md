# Workflow Examples: CodeMind CLI

## Workflow A: Explain a Project

**User Command:**
```bash
codemind "Explain this project"
```

**Agent Actions:**
1. Calls `list_directory(".")` to inspect project top-level structure.
2. Identifies build manifest (`pyproject.toml`, `package.json`, etc.) and reads it.
3. Reads `README.md` if present.
4. Identifies entry points (e.g. `src/main.py`) and lists major modules.
5. Emits clear final explanation citing specific file paths, architecture summary, and how to run tests.
6. Does not modify any files.

---

## Workflow B: Build a Feature

**User Command:**
```bash
codemind "Add an auth token verification helper to src/auth.py"
```

**Agent Actions:**
1. Inspects existing project structure and dependency files.
2. Formulates a 3-step structured plan:
   - Step 1: Create `src/auth.py` with JWT token verification.
   - Step 2: Add unit tests in `tests/test_auth.py`.
   - Step 3: Run the test suite.
3. Proposes `create_file` for `src/auth.py`.
4. In supervised mode: prompts developer with file content preview.
5. Proposes unit test creation.
6. Runs test runner (`pytest` or `unittest`).
7. Honest summary shows: files created, test executed, exit code 0.

---

## Workflow C: Debug a Failing Test

**User Command:**
```bash
codemind "Fix the failing test in tests/test_calc.py"
```

**Agent Actions:**
1. Runs project test runner to reproduce failure and capture traceback.
2. Reads failing test and corresponding source module.
3. Diagnoses bug using error evidence.
4. Proposes targeted patch via `apply_patch` preserving surrounding lines.
5. Re-runs test runner.
6. Verifies pass status and reports root cause and resolution.
