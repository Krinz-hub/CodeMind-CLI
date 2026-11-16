"""Installation and self-update CLI command for CodeMind (codemind install).

Sets up the dedicated virtual environment, installs dependencies, and creates
the global launcher executable in ~/.local/bin/codemind.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console

from codemind.cli.ui import TerminalUI
from codemind.launcher import find_codemind_venv


def run_install(
    user_bin_dir: Optional[Path] = None,
    venv_dir: Optional[Path] = None,
    plain: bool = False,
) -> int:
    """Execute installation / self-configuration procedure."""
    console = Console(no_color=plain)

    # 1. Determine Repository Root
    pkg_file = Path(__file__).resolve()
    repo_root = pkg_file.parent.parent.parent.parent

    target_bin_dir = user_bin_dir or (Path.home() / ".local" / "bin")
    target_bin_dir.mkdir(parents=True, exist_ok=True)

    target_venv = venv_dir or find_codemind_venv() or (repo_root / ".venv")

    console.print(f"\n[bold cyan]▟●▙ CodeMind Global CLI Installer[/bold cyan]")
    console.print(f"Repository Root : {repo_root}")
    console.print(f"Target Venv     : {target_venv}")
    console.print(f"Global Bin Dir  : {target_bin_dir}\n")

    # 2. Setup Virtual Environment
    if not (target_venv / "bin" / "python").is_file():
        console.print(f"[*] Creating Python virtual environment at {target_venv}...")
        try:
            subprocess.run([sys.executable, "-m", "venv", str(target_venv)], check=True)
            console.print("    [green]✓[/green] Virtual environment created successfully.")
        except subprocess.CalledProcessError as ex:
            console.print(f"    [red]✗[/red] Failed to create virtual environment: {ex}")
            return 1
    else:
        console.print(f"[*] Found existing virtual environment at {target_venv}.")

    venv_pip = target_venv / "bin" / "pip"
    venv_py = target_venv / "bin" / "python"

    # 3. Install Package into Venv
    console.print(f"[*] Installing CodeMind package into {target_venv}...")
    try:
        subprocess.run(
            [str(venv_pip), "install", "-e", str(repo_root)],
            check=True,
            stdout=subprocess.DEVNULL if not plain else None,
            stderr=subprocess.PIPE,
        )
        console.print("    [green]✓[/green] Package dependencies installed.")
    except subprocess.CalledProcessError as ex:
        console.print(f"    [red]✗[/red] Failed to install package via pip: {ex.stderr.decode() if ex.stderr else ex}")
        return 1

    # 4. Link or Install Global Launcher Executable
    global_launcher = target_bin_dir / "codemind"
    venv_codemind = target_venv / "bin" / "codemind"

    console.print(f"[*] Configuring global command at {global_launcher}...")
    if venv_codemind.is_file():
        try:
            if global_launcher.is_symlink() or global_launcher.is_file():
                global_launcher.unlink()
            global_launcher.symlink_to(venv_codemind)
            global_launcher.chmod(0o755)
            console.print(f"    [green]✓[/green] Symlinked {global_launcher} -> {venv_codemind}")
        except Exception as ex:
            console.print(f"    [yellow]![/yellow] Symlink failed ({ex}), copying launcher script...")
            shutil.copy2(venv_codemind, global_launcher)
            global_launcher.chmod(0o755)
    else:
        console.print(f"    [yellow]![/yellow] {venv_codemind} not found; generating entry wrapper...")
        wrapper_content = f"""#!/usr/bin/env bash
exec "{target_venv}/bin/python" -m codemind.cli.main "$@"
"""
        global_launcher.write_text(wrapper_content)
        global_launcher.chmod(0o755)
        console.print(f"    [green]✓[/green] Generated executable script at {global_launcher}")

    # 5. Check PATH accessibility
    path_env = os.environ.get("PATH", "")
    in_path = str(target_bin_dir) in path_env.split(":")

    console.print("\n" + "=" * 50)
    if in_path:
        console.print("[bold green]✓ CodeMind is globally installed and available on PATH![/bold green]")
        console.print(f"You can now run: [bold cyan]codemind[/bold cyan] from any directory.")
    else:
        console.print("[bold yellow]! Installation complete, but bin directory is not in PATH.[/bold yellow]")
        console.print(f"Add the following line to your ~/.bashrc or ~/.zshrc:")
        console.print(f'    export PATH="{target_bin_dir}:$PATH"\n')
        console.print("Then run: source ~/.bashrc")

    console.print("\nNext step: Run [bold cyan]codemind doctor[/bold cyan] to verify system health.")
    return 0
