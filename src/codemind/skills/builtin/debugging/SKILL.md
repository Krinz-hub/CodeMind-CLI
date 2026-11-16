---
name: debugging
version: 1.0.0
description: Systematic root-cause diagnosis, reproduction steps, minimal patch application, and regression verification.
category: debugging
triggers:
  manifests: []
  globs: []
  keywords:
    - "debug"
    - "bug"
    - "fix"
    - "error"
    - "exception"
    - "traceback"
    - "failing"
    - "crash"
    - "defect"
    - "issue"
required_tools:
  - read_file
  - apply_patch
  - run_command
dependencies: []
conflicts: []
workflow_steps:
  - "1. Reproduce First: Run the failing test or command to observe the exact stack trace, error message, and reproduction conditions."
  - "2. Trace Data Flow: Read the relevant source files and trace inputs backward from the failure point to where faulty assumptions were made."
  - "3. Identify Root Cause: Distinguish between superficial symptoms (e.g. NoneType error) and root cause (e.g. missing validation or unhandled state transition)."
  - "4. Formulate Minimal Patch: Apply targeted changes using `apply_patch`, avoiding wide-scale cosmetic refactorings."
  - "5. Add Regression Test: Create or update an automated test that specifically reproduces and guards against this defect in the future."
  - "6. Re-verify Clean Execution: Run the full project test suite to confirm the defect is resolved and no regressions were introduced."
constraints:
  - "Never propose speculative fixes without reading the failing code lines and observing the stack trace."
  - "Never swallow exceptions with empty `except:` or `catch (e) {}` blocks as a fix."
  - "Preserve unrelated comments, existing architecture, and nearby formatting when editing files."
verification:
  - "Re-run the reproduction test command and verify that it transitions from FAIL to PASS."
enabled: true
---

# Systematic Debugging Protocol

## 1. Core Rule: Reproduce Before Mutating
Speculative editing without reproducing the failure introduces secondary regressions. Always trigger the failure first to understand the execution context and expected vs actual behavior.

## 2. Root Cause vs Symptom
- **Symptom:** `AttributeError: 'NoneType' object has no attribute 'id'`
- **Superficial Fix (Anti-pattern):** `if user is not None: return user.id` (swallows problem silently)
- **Root Cause Diagnosis:** Why was `user` None in the first place? Did the repository lookup fail, or was the session token unverified?
- **True Fix:** Guard lookup failure with explicit domain error or correct token validation pipeline.
