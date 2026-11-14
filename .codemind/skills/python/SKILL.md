---
name: python-best-practices
description: Core Python idiomatic standards, typing, and testing rules.
triggers:
  - "*.py"
  - "pyproject.toml"
  - "setup.py"
  - "requirements.txt"
---

# Python Engineering Guidelines

1. **Typing & Signatures:**
   - Always include type annotations for function parameters and return values.
   - Use `from __future__ import annotations` when using modern Python 3.10+ union types (`int | None`).

2. **Error Handling:**
   - Never use bare `except:` clauses. Always catch explicit exception subclasses.
   - Provide informative error messages with context.

3. **Testing Standards:**
   - Author hermetic unit tests using `unittest` or `pytest`.
   - Never write tests that require live external network or unmocked web APIs.

4. **Code Quality:**
   - Adhere to PEP 8 standards.
   - Keep functions concise with a single, clear responsibility.
