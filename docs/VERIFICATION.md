# Verification & Honest Completion: CodeMind CLI

## 1. Principle of Honest Completion

A fundamental flaw of many coding assistants is hallucinated success—stating that "the build succeeded" or "the tests pass" when no check was actually performed.

CodeMind CLI enforces the **Honest Verification Principle**:
- Code generation ≠ File modified.
- File modified ≠ Code compiles.
- Code compiles ≠ Tests pass.
- Tests pass ≠ Task satisfies all requirements.

---

## 2. Verification Pipeline

```text
[Task Modification Applied]
          │
          ▼
[1. Diff Analysis]
          Examine unified diff to detect affected files and functions.
          │
          ▼
[2. Check Discovery]
          Discover relevant test/build commands based on project manifests:
          - Python: pytest, python3 -m unittest
          - Node/TypeScript: npm test, npx vitest, npm run build
          - Rust: cargo test, cargo check
          - Go: go test ./...
          │
          ▼
[3. Test Execution & Result Parsing]
          Execute command with timeout and process sandbox.
          Extract passed/failed test counts, error backtraces, and exit code.
          │
          ▼
[4. Honest Completion Report]
          Generate completion record explicitly itemizing:
          - Files Created: [list]
          - Files Modified: [list]
          - Checks Executed: [commands]
          - Checks Passed: [names / counts]
          - Checks Failed: [names / error excerpts]
          - Unverified Components: [items not covered by tests]
```
