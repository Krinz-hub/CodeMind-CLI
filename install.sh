#!/usr/bin/env bash
# ==============================================================================
# CodeMind CLI — One-Command Global Installer
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$SCRIPT_DIR"
VENV_DIR="${REPO_DIR}/.venv"
BIN_DIR="${HOME}/.local/bin"

echo "============================================================"
echo "▟●▙ CodeMind CLI — Universal Global Launcher Setup"
echo "============================================================"

# 1. Discover suitable Python (>= 3.10)
PYTHON_BIN=""
for candidate in python3 python python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PY_VER="$("$candidate" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || true)"
        MAJOR=$(echo "$PY_VER" | cut -d. -f1)
        MINOR=$(echo "$PY_VER" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            PYTHON_BIN="$(command -v "$candidate")"
            echo "✓ Found compatible Python: $PYTHON_BIN (v$PY_VER)"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "Error: Python 3.10 or higher is required. Please install python3.10+ and re-run." >&2
    exit 1
fi

# 2. Setup Virtual Environment
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at $VENV_DIR..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
else
    echo "✓ Existing virtual environment found at $VENV_DIR"
fi

# 3. Install Package and Dependencies
echo "Installing CodeMind CLI and dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e "$REPO_DIR"
echo "✓ Package installed in editable mode."

# 4. Install Global Executable into ~/.local/bin
mkdir -p "$BIN_DIR"
GLOBAL_EXEC="$BIN_DIR/codemind"
VENV_EXEC="$VENV_DIR/bin/codemind"

if [ -f "$VENV_EXEC" ]; then
    ln -sf "$VENV_EXEC" "$GLOBAL_EXEC"
    chmod +x "$GLOBAL_EXEC"
    echo "✓ Linked $GLOBAL_EXEC -> $VENV_EXEC"
else
    echo "#!/usr/bin/env bash" > "$GLOBAL_EXEC"
    echo "exec \"$VENV_DIR/bin/python\" -m codemind.cli.main \"\$@\"" >> "$GLOBAL_EXEC"
    chmod +x "$GLOBAL_EXEC"
    echo "✓ Created launcher at $GLOBAL_EXEC"
fi

# 5. Check PATH Accessibility
echo "------------------------------------------------------------"
case ":$PATH:" in
    *":$BIN_DIR:"*)
        echo "✓ Global binary directory ($BIN_DIR) is already in your PATH."
        ;;
    *)
        echo "! Warning: $BIN_DIR is NOT in your PATH."
        echo "Add the following line to your ~/.bashrc or ~/.zshrc:"
        echo "    export PATH=\"$BIN_DIR:\$PATH\""
        echo "Then run: source ~/.bashrc"
        ;;
esac

echo "============================================================"
echo "✓ Installation complete!"
echo "Verifying launcher..."
"$GLOBAL_EXEC" --version
echo "============================================================"
echo "Next: Run 'codemind doctor' to verify local model and tools."
