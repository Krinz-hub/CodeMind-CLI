# Tool System Specification: CodeMind CLI

## 1. Tool Architecture

Every tool in CodeMind CLI implements a strict contract:
- **Name & Description:** Documented purpose and capability.
- **Input Schema:** Strongly validated Pydantic model with descriptive field constraints.
- **Permission Level:** `READ_ONLY`, `READ_WRITE`, or `EXECUTE`.
- **Execution Hook:** Safe handler receiving validated arguments and execution context.
- **Normalized Output (`ToolResult`):** Standard schema containing `ok`, `content`, `stdout`, `stderr`, `exit_code`, and `truncated`.

---

## 2. Core Tool Registry

### 2.1 Filesystem Tools
- `read_file(path: str, offset: int = 1, limit: int = 200)`: Reads specified line slice with line numbers.
- `list_directory(path: str = ".", recursive: bool = False, max_depth: int = 2)`: Lists entries respecting ignore filters.
- `search_files(pattern: str, path: str = ".")`: Locates matching filenames using glob patterns.
- `search_text(query: str, path: str = ".", max_matches: int = 50)`: Greps project files for matching strings or regexes.
- `create_file(path: str, content: str)`: Creates a new file inside the workspace (requires approval in supervised mode).
- `apply_patch(path: str, patch_or_diff: str)`: Applies bounded unified diff or replacement block preserving surrounding lines.

### 2.2 Terminal Tools
- `run_command(command: str, timeout_seconds: int = 60)`: Executes a shell command inside workspace root.
  - Previews exact command to user in supervised mode before running.
  - Captures stdout/stderr with buffer limits (truncation safeguard).
  - Enforces hard timeout and terminates child process trees on timeout or cancel.

### 2.3 Git Inspection Tools
- `git_status()`: Summarizes untracked, modified, and staged files.
- `git_diff(staged: bool = False, path: str | None = None)`: Retrieves unified diff of current changes.
- `git_log(max_count: int = 5)`: Lists recent commits for context.

*Note: Git write operations (commit, push, checkout) are intentionally omitted from automatic tools to prevent unauthorized repository mutation.*
