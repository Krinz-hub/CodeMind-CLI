# Skills Subsystem: CodeMind CLI

## 1. Skill Architecture

Skills allow users and teams to equip CodeMind CLI with project- or domain-specific guidelines, testing idioms, and architecture patterns.

Skills live in `.codemind/skills/` within the repository or in the user's global config directory:
```text
.codemind/skills/
├── python/
│   └── SKILL.md
├── fastapi/
│   └── SKILL.md
└── debugging/
    └── SKILL.md
```

---

## 2. Skill Schema (`SKILL.md`)

Each `SKILL.md` contains frontmatter metadata followed by instructions:

```markdown
---
name: python-best-practices
description: Project formatting, typing, and testing guidelines for Python.
triggers:
  - "*.py"
  - "pyproject.toml"
  - "requirements.txt"
---

# Python Guidelines for this Project
- Always include type hints on public functions.
- Use pytest with standard assertions.
- Format with black / ruff standards.
```

---

## 3. Dynamic Activation

To preserve the context budget, skills are loaded **selectively**:
1. When workspace inspection reveals trigger files (e.g. `pyproject.toml` triggers python skills).
2. When the user prompt explicitly references a domain or technology.
3. Skills supply behavioral guidance only and cannot override the security sandbox or permission hierarchy.
