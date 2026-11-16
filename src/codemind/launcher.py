"""Universal Global CLI Launcher for CodeMind.

Enables 'codemind' to run from any terminal directory by:
1. Automatically locating and activating the CodeMind virtual environment without manual user intervention.
2. Checking critical dependency health.
3. Delegating to the primary Typer CLI application.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

REQUIRED_DEPENDENCIES = [
    ("typer", "typer"),
    ("rich", "rich"),
    ("pydantic", "pydantic"),
    ("httpx", "httpx"),
    ("click", "click"),
    ("yaml", "pyyaml"),
]


def find_codemind_venv() -> Optional[Path]:
    """Locate the most appropriate CodeMind virtual environment in priority order.

    1. Explicit CODEMIND_VENV environment variable.
    2. Repository development virtualenv (.venv at repository root).
    3. User global virtualenv (~/.codemind/venv).
    4. Local share virtualenv (~/.local/share/codemind/venv).
    5. Parent directory search for .venv adjacent to pyproject.toml.
    """
    # 1. Environment variable override
    env_override = os.environ.get("CODEMIND_VENV")
    if env_override:
        p = Path(env_override).expanduser().resolve()
        if (p / "bin" / "python").is_file() or (p / "bin" / "python3").is_file():
            return p

    # 2. Repository root .venv (derived from this file's location)
    try:
        launcher_file = Path(__file__).resolve()
        # src/codemind/launcher.py -> repo_root is 3 levels up
        repo_root = launcher_file.parent.parent.parent
        repo_venv = repo_root / ".venv"
        if (repo_venv / "bin" / "python").is_file() or (repo_venv / "bin" / "python3").is_file():
            return repo_venv
    except Exception:
        pass

    # 3. User global virtual environment in ~/.codemind/venv
    user_venv = Path.home() / ".codemind" / "venv"
    if (user_venv / "bin" / "python").is_file() or (user_venv / "bin" / "python3").is_file():
        return user_venv

    # 4. Local share virtual environment in ~/.local/share/codemind/venv
    share_venv = Path.home() / ".local" / "share" / "codemind" / "venv"
    if (share_venv / "bin" / "python").is_file() or (share_venv / "bin" / "python3").is_file():
        return share_venv

    # 5. CWD traversal (if user is running inside a project workspace with its own .venv)
    try:
        current = Path.cwd().resolve()
        for parent in [current] + list(current.parents):
            cwd_venv = parent / ".venv"
            if (cwd_venv / "bin" / "python").is_file() and (parent / "pyproject.toml").is_file():
                return cwd_venv
    except Exception:
        pass

    return None


def is_running_in_target_venv(target_venv: Optional[Path]) -> bool:
    """Determine whether the current process is already executing inside the target venv."""
    if os.environ.get("CODEMIND_VENV_ACTIVE") == "1":
        return True

    if target_venv is None:
        # If no specific venv required, check if we're in any virtualenv
        return sys.prefix != getattr(sys, "base_prefix", sys.prefix)

    try:
        current_prefix = Path(sys.prefix).resolve()
        expected_prefix = target_venv.resolve()
        if current_prefix == expected_prefix:
            return True

        current_exec = Path(sys.executable).resolve()
        venv_py = (target_venv / "bin" / "python").resolve()
        if current_exec == venv_py:
            return True
    except Exception:
        pass

    return False


def reexec_in_venv(target_venv: Path) -> None:
    """Seamlessly re-execute the current command under the specified virtualenv Python.

    Preserves all CLI arguments, environment variables, working directory, and terminal I/O.
    """
    venv_py = target_venv / "bin" / "python"
    if not venv_py.is_file():
        venv_py = target_venv / "bin" / "python3"

    if not venv_py.is_file():
        return

    new_env = os.environ.copy()
    new_env["CODEMIND_VENV_ACTIVE"] = "1"
    new_env["VIRTUAL_ENV"] = str(target_venv)
    new_env["PATH"] = f"{target_venv / 'bin'}:{new_env.get('PATH', '')}"

    args = [str(venv_py), "-m", "codemind.cli.main"] + sys.argv[1:]
    os.execve(str(venv_py), args, new_env)


def check_missing_dependencies() -> list[str]:
    """Check if all required third-party packages are installed in the active environment."""
    missing: list[str] = []
    for mod_name, pkg_name in REQUIRED_DEPENDENCIES:
        if importlib.util.find_spec(mod_name) is None:
            missing.append(pkg_name)
    return missing


def main() -> None:
    """Global CLI launcher entry point."""
    # 1. Auto-discover and activate the CodeMind virtual environment if needed
    if os.environ.get("CODEMIND_NO_VENV") != "1":
        target_venv = find_codemind_venv()
        if target_venv and not is_running_in_target_venv(target_venv):
            reexec_in_venv(target_venv)
            return

    # 2. Verify dependencies
    missing = check_missing_dependencies()
    if missing:
        sys.stderr.write(
            f"\n\033[1;31m[CM Error] Missing required dependencies:\033[0m {', '.join(missing)}\n\n"
            f"CodeMind requires these packages to operate.\n"
            f"To install them into the current environment, run:\n"
            f"    \033[1;32mpip install {' '.join(missing)}\033[0m\n\n"
            f"Or run the CodeMind installer:\n"
            f"    \033[1;32m./install.sh\033[0m\n\n"
        )
        sys.exit(1)

    # 3. Hand over control to primary CLI application
    from codemind.cli.main import app

    app()


if __name__ == "__main__":
    main()
