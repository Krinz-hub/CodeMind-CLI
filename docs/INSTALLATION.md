# CodeMind Global CLI Launcher & Installation Guide

This document describes how to install, configure, verify, and run **CodeMind CLI** as a global, one-command tool from any terminal directory.

---

## 1. Quickstart: One-Command Installation

To install CodeMind globally on your system:

```bash
# Clone the repository
git clone https://github.com/codemind/codemind-cli.git
cd "codemind cli"

# Run the installer
./install.sh
```

The installer will:
1. Detect Python (>= 3.10).
2. Create or reuse the dedicated virtual environment (`.venv`).
3. Install CodeMind in editable mode with all dependencies.
4. Create the global launcher executable at `~/.local/bin/codemind`.
5. Verify PATH accessibility and command execution.

---

## 2. Using CodeMind Globally

Once installed, you can invoke CodeMind from **any terminal directory**:

```bash
# Start CodeMind interactive companion (Milo)
codemind

# Run a one-shot autonomous task
codemind "Refactor auth middleware in src/auth.py to add JWT validation"

# Run system and model diagnostics
codemind doctor

# Show version and global help
codemind --version
codemind --help
```

---

## 3. How the Global Launcher Works

CodeMind uses an intelligent, two-tier launcher architecture (`src/codemind/launcher.py`):

1. **Virtual Environment Auto-Discovery**:
   When `codemind` is invoked from any directory (even without activating `.venv`), the launcher automatically searches for the CodeMind virtual environment in the following order:
   - `CODEMIND_VENV` environment variable override.
   - Development repository `.venv` (`<repo_root>/.venv`).
   - User global virtual environment (`~/.codemind/venv`).
   - Local share virtual environment (`~/.local/share/codemind/venv`).
   - Active workspace virtual environment (`.venv` adjacent to `pyproject.toml`).

2. **Zero-Overhead In-Place Re-Execution**:
   If the launcher is invoked using system Python or an outside environment, it immediately re-executes itself in-place via `os.execve` using the virtual environment's Python binary. This preserves:
   - Full virtual environment isolation and pinned dependencies.
   - All CLI flags and arguments.
   - Standard input/output/error streams and ANSI TTY colors.
   - The user's current working directory.

3. **Dependency Verification**:
   If required packages (`typer`, `rich`, `pydantic`, `httpx`, `pyyaml`, `click`) are missing or corrupted, the launcher intercepts the error and presents clear remediation commands instead of an unformatted Python traceback.

---

## 4. Local Model Service Management

Before entering the interactive companion or executing a task, CodeMind automatically verifies and manages the local inference provider:

### Ollama (Default: `qwen3.6:35b` on `http://127.0.0.1:11434`)
- **Automated Health Check**: CodeMind polls `/api/tags` to ensure the Ollama service is responsive and the target model is loaded.
- **Safe Auto-Start**: If the Ollama daemon is offline and the `ollama` executable is detected on `PATH`, CodeMind attempts to launch `ollama serve` in the background and polls until the socket is ready.
- **Remediation**: If Ollama cannot be reached, CodeMind provides clear commands to start it manually or switch to offline mock mode:
  ```bash
  ollama serve
  ollama pull qwen3.6:35b
  codemind --provider mock
  ```

### CodeMind Custom Model (`http://127.0.0.1:8000/v1`)
- **Service Discrimination**: Inspects service signatures on port 8000 to prevent false-readiness collisions with foreign applications.
- **Transparent Fallback**: If the custom server is offline, requests automatically route to local Ollama (`qwen3.6:35b`) with full diagnostic tracking.

---

## 5. System Diagnostics: `codemind doctor`

Run `codemind doctor` to inspect your complete environment:

```bash
codemind doctor
```

The diagnostic suite evaluates 18 health checks across:
- **Python Environment**: Version, active/discovered virtual environment, binary path.
- **Dependencies**: `typer`, `rich`, `pydantic`, `httpx`, `click`, `pyyaml`.
- **Packaging & Launcher**: Global PATH binary, pip distribution metadata.
- **Inference Providers**: Ollama executable, daemon connectivity, pulled models list, target model readiness, custom model fallback state.
- **Workspace & Tools**: Git CLI, workspace write permissions, SQLite FTS5 project memory, skills engine discovery.

Use `codemind doctor --plain` for unformatted, plain-text output suitable for automated CI pipelines or headless scripts.

---

## 6. Self-Update and Reconfiguration

To update the launcher or reconfigure binary links:

```bash
# Reinstall / update via CLI
codemind install

# Or specify custom bin and venv paths:
codemind install --bin-dir /usr/local/bin --venv ~/.codemind/venv
```

---

## 7. PATH Configuration

If the `codemind` command is not recognized after installation, ensure that `~/.local/bin` is in your shell `PATH`:

```bash
# Add to ~/.bashrc or ~/.zshrc
export PATH="$HOME/.local/bin:$PATH"

# Reload your shell profile
source ~/.bashrc  # or source ~/.zshrc
```
