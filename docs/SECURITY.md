# Security & Sandboxing Specification: CodeMind CLI

## 1. Threat Model & Philosophy

AI coding models are probabilistic generation systems and must be treated as untrusted actors regarding operating system authority. An instruction from a model cannot elevate its own permissions. Untrusted content ingested from files, web responses, or build logs cannot override system safety policy.

---

## 2. Security Boundaries

### 2.1 Workspace Sandboxing
- **Canonicalization:** Every target path is resolved to its real canonical path using `os.path.realpath()` before any disk I/O.
- **Traversal Prevention:** Any path that resolves outside the designated workspace root triggers a `SecurityViolationError` and halts the action.
- **Symlink Escapes:** Symlinks pointing outside the workspace root are treated as foreign paths and access is rejected unless explicitly whitelisted by the user.

### 2.2 Permission Modes
1. **`read-only`:**
   - Only tools marked `READ_ONLY` (`read_file`, `list_directory`, `search_files`, `search_text`, `git_status`, `git_diff`) are permitted.
   - Any write or command execution is blocked immediately.
2. **`supervised` (Default):**
   - Read operations execute automatically.
   - Any file modification (`create_file`, `apply_patch`) or terminal execution (`run_command`) requires explicit interactive human approval with diff / command preview.
3. **`trusted`:**
   - Low-risk read and write operations inside the workspace root are executed without per-action prompts.
   - High-risk operations (destructive deletions, command executions outside project scope, git branch switches) still require approval.

### 2.3 Secret Shielding & Redaction
- Files matching secret patterns (`.env`, `*.pem`, `*.key`, `id_rsa`, `*secret*`, `*credentials*`) are barred from tool reading by default.
- Real-time stream redactor masks credential patterns (OpenAI keys, GitHub tokens, AWS access keys, JWTs) before tool results are recorded into session histories or displayed in the terminal.
