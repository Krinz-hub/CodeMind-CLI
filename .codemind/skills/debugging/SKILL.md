---
name: systematic-debugging
description: Root-cause diagnosis and regression test strategy for bug fixes.
triggers:
  - "*debug*"
  - "*fix*"
  - "*error*"
---

# Systematic Debugging Protocol

1. **Reproduce First:**
   - Execute the failing test or command to observe the exact stack trace and failure mode.
   - Do not propose speculative fixes before reproducing the symptom.

2. **Isolate Root Cause:**
   - Read the relevant module lines and trace inputs to where assumptions failed.

3. **Minimal Targeted Patch:**
   - Use `apply_patch` to make the minimal essential correction.
   - Preserve surrounding code, comments, and unrelated formatting.

4. **Add Regression Test:**
   - Whenever feasible, add an automated test that specifically guards against this defect.

5. **Re-verify:**
   - Run the project test suite to verify that the fix passes and introduces zero regressions.
