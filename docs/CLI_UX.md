# CLI User Experience: CodeMind CLI

## 1. Visual Language & Terminal Ergonomics

CodeMind CLI is built for developers who spend entire days in terminal windows. The visual design is restrained, professional, and readable.

### Palette:
- **Graphite / Charcoal:** Primary borders and secondary text.
- **Off-White / Cyan:** Body text, headers, and code snippets.
- **Muted Amber / Orange:** Milo status accents, attention items, approvals.
- **Emerald Green:** Successful verification, passing tests, completed tasks.
- **Crimson Red:** Blocked tasks, test failures, security violations.

---

## 2. Interactive Terminal States

1. **Ready:** Milo brand mark displayed with model, provider, and workspace summary.
2. **Thinking:** Subtle spinner indicator while local model generates response.
3. **Inspecting:** Informative list of project files being scanned or read.
4. **Planning:** Real-time table displaying task IDs, titles, and live status.
5. **Approval Required:** Prompts user with full diff or exact shell command to confirm or deny.
6. **Executing:** Streaming command output or patch progress.
7. **Verifying:** Running project tests and displaying pass/fail statistics.
8. **Summary:** Final breakdown of files changed, checks run, and session resumption ID.

---

## 3. Accessibility & Plain Mode

When invoked with `--plain` or `--no-color` (or when `NO_COLOR` is detected in the environment):
- ANSI color codes are completely disabled.
- Unicode symbols degrade to plain ASCII equivalents (`[v]`, `[x]`, `[*]`, `-->`).
- Terminal animations are disabled.
