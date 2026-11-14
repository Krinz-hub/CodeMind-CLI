# Implementation Roadmap: CodeMind CLI

## Phase Progression

| Phase | Title | Scope | Acceptance Criteria |
|---|---|---|---|
| **Phase 0** | **Repository Audit & Design** | Environment inspection, architecture, specs, and file layout. | All 17 design docs complete, clean workspace initialized, no external dependencies required. |
| **Phase 1** | **CLI Foundation** | CLI entry point, Milo welcome screen, Rich UI, config loader. | `codemind --help`, `codemind --version`, status check, and plain mode. |
| **Phase 2** | **Model Adapter** | `ModelAdapter` ABC, `CodeMindLocalAdapter`, `OllamaAdapter`, `MockModelAdapter`. | Health checks pass, mock adapter generates structured test responses hermetically. |
| **Phase 3** | **Agent Loop** | Bounded multi-turn loop, v1 protocol envelope parser, turn limits, error loopback. | Mock model requests tool, receives observation, reaches validated final completion. |
| **Phase 4** | **Read-Only Project Tools** | `read_file`, `list_directory`, `search_files`, `search_text`, ignore engine, secret shield. | Agent explores workspace, respects ignore patterns, refuses to read outside workspace or read secrets. |
| **Phase 5** | **Safe Editing** | `create_file`, `apply_patch`, unified diff viewer, approval workflow. | Agent proposes patches, presents clean diffs, blocks traversal, applies changes only after approval. |
| **Phase 6** | **Terminal Execution** | `run_command`, output capping, timeouts, process tree termination. | Agent executes approved commands, captures stdout/stderr, terminates timeouts safely. |
| **Phase 7** | **Planning & Context** | Structured task DAGs, status transitions, context token budget allocator. | Multi-step task plan authored, tracked, and updated with tangible evidence per step. |
| **Phase 8** | **Sessions & Memory** | Disk persistence under `.codemind/sessions/`, session resume, redacted audit trail. | Interrupted sessions restored with full task state, chat history, and diff summaries. |
| **Phase 9** | **Verification** | Test runner discovery, check execution, honest completion synthesis. | Agent executes test suites, distinguishes verified successes from unverified changes. |
| **Phase 10**| **Skills & Instructions** | `.codemind/skills/` loader, frontmatter matching, scoped skill injection. | Relevant skills loaded selectively into context without compromising security boundaries. |
