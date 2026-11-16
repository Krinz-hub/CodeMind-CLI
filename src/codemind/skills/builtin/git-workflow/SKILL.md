---
name: git-workflow
version: 1.0.0
description: Professional Git version control hygiene, atomic commits, conventional commit syntax, and pull request preparation.
category: workflow
triggers:
  manifests:
    - ".gitignore"
  globs:
    - ".git*"
  keywords:
    - "git"
    - "commit"
    - "branch"
    - "rebase"
    - "pr"
    - "pull request"
    - "merge"
    - "diff"
    - "stash"
required_tools:
  - git_status
  - git_diff
  - run_command
dependencies: []
conflicts: []
workflow_steps:
  - "1. Inspect working tree status (`git status`) to identify modified, added, and untracked files."
  - "2. Review unstaged changes via `git diff` to ensure only intended files are touched; verify no secrets or temp files exist."
  - "3. Structure atomic commits grouping logically related changes together."
  - "4. Format commit messages following the Conventional Commits specification (feat:, fix:, chore:, refactor:, test:, docs:)."
  - "5. Verify that branch builds cleanly and test suite passes before proposing branch merge or pull request."
constraints:
  - "Never commit temporary build artifacts, `.env` files, credentials, or IDE directories (`.vscode`, `.idea`)."
  - "Never use vague commit messages like 'fixed stuff' or 'update'; describe the exact technical change and motivation."
  - "Do not execute destructive Git operations (`git reset --hard`, `git push --force`) without explicit user instruction."
verification:
  - "Execute git_status and verify working tree is clean or staged as expected."
enabled: true
---

# Git Version Control & Hygiene Protocol

## 1. Conventional Commits Syntax
```
<type>(<optional scope>): <short description in imperative mood>

[optional body explaining motivation and trade-offs]

[optional footer(s), e.g., Closes #123]
```

### Commit Types:
- `feat`: A new user-facing or programmatic feature.
- `fix`: A bug fix or defect correction.
- `refactor`: Code change that neither fixes a bug nor adds a feature.
- `test`: Adding missing tests or correcting existing tests.
- `chore`: Build process, dependency updates, or tool configurations.
- `docs`: Documentation-only updates.

## 2. Pre-Commit Checklist
1. Inspect `git_diff` for stray print statements or temporary debugging logs.
2. Confirm `.gitignore` catches any local SQLite or temporary testing files.
