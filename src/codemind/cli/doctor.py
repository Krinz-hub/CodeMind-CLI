"""System diagnostics and health check for CodeMind CLI (codemind doctor).

Inspects:
1. Python environment and virtual environment discovery.
2. Required third-party dependencies.
3. Global CLI packaging and PATH accessibility.
4. Local model inference provider connectivity and pulled models.
5. Workspace storage, SQLite memory, and skills registry.
"""

from __future__ import annotations

import importlib.metadata
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from codemind import __brand_mark__, __version__
from codemind.cli.branding import COLOR_ACCENT, COLOR_DANGER, COLOR_INFO, COLOR_MUTED, COLOR_SUCCESS, COLOR_WARNING
from codemind.cli.ui import TerminalUI
from codemind.config import CodeMindConfig, ModelProvider
from codemind.launcher import find_codemind_venv, is_running_in_target_venv
from codemind.models.service_manager import is_ollama_running


@dataclass
class DiagnosticResult:
    category: str
    name: str
    status: str  # "PASS", "WARN", "FAIL"
    message: str
    remediation: Optional[str] = None


def check_python_environment() -> list[DiagnosticResult]:
    """Inspect Python version, venv status, and executable path."""
    results: list[DiagnosticResult] = []

    # 1. Python version
    v = sys.version_info
    v_str = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 10):
        results.append(
            DiagnosticResult(
                category="Python Environment",
                name="Python Version",
                status="PASS",
                message=f"Python {v_str} (>= 3.10 required)",
            )
        )
    else:
        results.append(
            DiagnosticResult(
                category="Python Environment",
                name="Python Version",
                status="FAIL",
                message=f"Python {v_str} is below required 3.10",
                remediation="Upgrade to Python 3.10 or higher.",
            )
        )

    # 2. Virtual Environment
    active_venv = os.environ.get("VIRTUAL_ENV") or (sys.prefix if sys.prefix != getattr(sys, "base_prefix", sys.prefix) else None)
    discovered_venv = find_codemind_venv()

    if active_venv:
        results.append(
            DiagnosticResult(
                category="Python Environment",
                name="Virtual Environment",
                status="PASS",
                message=f"Active: {active_venv}",
            )
        )
    elif discovered_venv:
        results.append(
            DiagnosticResult(
                category="Python Environment",
                name="Virtual Environment",
                status="PASS",
                message=f"Discovered: {discovered_venv} (auto-switched by launcher)",
            )
        )
    else:
        results.append(
            DiagnosticResult(
                category="Python Environment",
                name="Virtual Environment",
                status="WARN",
                message="Running on system Python without dedicated .venv",
                remediation="Run './install.sh' to create an isolated .venv in the repository.",
            )
        )

    # 3. Python Executable
    results.append(
        DiagnosticResult(
            category="Python Environment",
            name="Executable Path",
            status="PASS",
            message=str(sys.executable),
        )
    )

    return results


def check_dependencies() -> list[DiagnosticResult]:
    """Inspect critical runtime dependencies."""
    results: list[DiagnosticResult] = []
    deps = [
        ("typer", "typer"),
        ("rich", "rich"),
        ("pydantic", "pydantic"),
        ("httpx", "httpx"),
        ("click", "click"),
        ("pyyaml", "yaml"),
    ]

    for pkg_name, mod_name in deps:
        try:
            mod = __import__(mod_name)
            ver = getattr(mod, "__version__", None)
            if not ver:
                try:
                    ver = importlib.metadata.version(pkg_name)
                except Exception:
                    ver = "installed"
            results.append(
                DiagnosticResult(
                    category="Dependencies",
                    name=pkg_name,
                    status="PASS",
                    message=f"v{ver}",
                )
            )
        except ImportError:
            results.append(
                DiagnosticResult(
                    category="Dependencies",
                    name=pkg_name,
                    status="FAIL",
                    message="Missing package",
                    remediation=f"Run: pip install {pkg_name}",
                )
            )

    return results


def check_cli_launcher() -> list[DiagnosticResult]:
    """Inspect global CLI installation and PATH status."""
    results: list[DiagnosticResult] = []

    # 1. codemind binary on PATH
    cmd_path = shutil.which("codemind")
    if cmd_path:
        results.append(
            DiagnosticResult(
                category="Packaging & Launcher",
                name="Global Command",
                status="PASS",
                message=f"Found at {cmd_path}",
            )
        )
    else:
        results.append(
            DiagnosticResult(
                category="Packaging & Launcher",
                name="Global Command",
                status="WARN",
                message="'codemind' not found on system PATH",
                remediation="Ensure ~/.local/bin is in your PATH: export PATH=\"$HOME/.local/bin:$PATH\"",
            )
        )

    # 2. Package installation
    try:
        pkg_ver = importlib.metadata.version("codemind-cli")
        results.append(
            DiagnosticResult(
                category="Packaging & Launcher",
                name="Package 'codemind-cli'",
                status="PASS",
                message=f"v{pkg_ver} installed",
            )
        )
    except Exception:
        results.append(
            DiagnosticResult(
                category="Packaging & Launcher",
                name="Package 'codemind-cli'",
                status="WARN",
                message="Not installed via pip/setuptools metadata",
                remediation="Run: pip install -e .",
            )
        )

    return results


def check_local_model_services(config: CodeMindConfig) -> list[DiagnosticResult]:
    """Inspect local inference provider connectivity and pulled models."""
    results: list[DiagnosticResult] = []

    # 1. Ollama CLI binary
    ollama_bin = shutil.which("ollama")
    if ollama_bin:
        results.append(
            DiagnosticResult(
                category="Inference Provider",
                name="Ollama Executable",
                status="PASS",
                message=f"Found at {ollama_bin}",
            )
        )
    else:
        results.append(
            DiagnosticResult(
                category="Inference Provider",
                name="Ollama Executable",
                status="WARN",
                message="Ollama CLI not detected on PATH",
                remediation="Install Ollama from https://ollama.com",
            )
        )

    # 2. Ollama Service Connectivity
    ollama_endpoint = config.model.endpoint if config.model.provider == ModelProvider.OLLAMA else config.model.fallback_endpoint
    running, models = is_ollama_running(ollama_endpoint, timeout=2.0)

    if running:
        results.append(
            DiagnosticResult(
                category="Inference Provider",
                name="Ollama Service",
                status="PASS",
                message=f"Active at {ollama_endpoint} ({len(models)} model(s) pulled)",
            )
        )

        # Check configured model
        target = config.model.model_name
        has_target = any(target == m or m.startswith(f"{target}:") or target.startswith(f"{m}:") for m in models)
        if has_target:
            results.append(
                DiagnosticResult(
                    category="Inference Provider",
                    name="Target Model",
                    status="PASS",
                    message=f"Model '{target}' ready",
                )
            )
        else:
            results.append(
                DiagnosticResult(
                    category="Inference Provider",
                    name="Target Model",
                    status="WARN",
                    message=f"Model '{target}' not found in Ollama library. Available: {', '.join(models) or 'none'}",
                    remediation=f"Pull model: ollama pull {target}",
                )
            )
    else:
        results.append(
            DiagnosticResult(
                category="Inference Provider",
                name="Ollama Service",
                status="WARN",
                message=f"Unreachable at {ollama_endpoint}",
                remediation="Start Ollama service: ollama serve",
            )
        )

    # 3. Custom Model Provider (if enabled or fallback)
    if config.model.provider == ModelProvider.CODEMIND_CUSTOM:
        results.append(
            DiagnosticResult(
                category="Inference Provider",
                name="CodeMind Custom",
                status="PASS" if config.model.enable_fallback else "WARN",
                message=f"Endpoint: {config.model.endpoint} (Fallback to {config.model.fallback_model} enabled: {config.model.enable_fallback})",
            )
        )

    return results


def check_workspace_and_tools(workspace: Path) -> list[DiagnosticResult]:
    """Inspect workspace directory, Git, SQLite memory, and skills."""
    results: list[DiagnosticResult] = []

    # 1. Git availability
    git_bin = shutil.which("git")
    if git_bin:
        results.append(
            DiagnosticResult(
                category="Workspace & Tools",
                name="Git CLI",
                status="PASS",
                message=f"Found at {git_bin}",
            )
        )
    else:
        results.append(
            DiagnosticResult(
                category="Workspace & Tools",
                name="Git CLI",
                status="WARN",
                message="Git executable not found on PATH",
                remediation="Install git (e.g. sudo apt install git).",
            )
        )

    # 2. Workspace writable
    ws_writable = os.access(workspace, os.W_OK)
    results.append(
        DiagnosticResult(
            category="Workspace & Tools",
            name="Workspace Directory",
            status="PASS" if ws_writable else "FAIL",
            message=f"{workspace} ({'writable' if ws_writable else 'read-only'})",
            remediation=f"Ensure write permissions on {workspace}" if not ws_writable else None,
        )
    )

    # 3. Project Memory
    from codemind.memory.store import SQLiteProjectMemory

    try:
        mem = SQLiteProjectMemory(workspace)
        stats = mem.get_stats()
        results.append(
            DiagnosticResult(
                category="Workspace & Tools",
                name="Project Memory (FTS5)",
                status="PASS",
                message=f"SQLite ready ({getattr(stats, 'total_records', 0)} record(s))",
            )
        )
    except Exception as ex:
        results.append(
            DiagnosticResult(
                category="Workspace & Tools",
                name="Project Memory (FTS5)",
                status="WARN",
                message=f"Initialization error: {ex}",
            )
        )

    # 4. Skills Registry
    from codemind.skills.registry import SkillRegistry

    try:
        skills = SkillRegistry(workspace)
        count = len(skills.discover_all())
        results.append(
            DiagnosticResult(
                category="Workspace & Tools",
                name="Skills Engine",
                status="PASS",
                message=f"{count} skill(s) registered",
            )
        )
    except Exception as ex:
        results.append(
            DiagnosticResult(
                category="Workspace & Tools",
                name="Skills Engine",
                status="WARN",
                message=f"Skills loading error: {ex}",
            )
        )

    return results


def run_doctor(config: CodeMindConfig, plain: bool = False) -> int:
    """Run full diagnostics suite and print formatted results.

    Returns exit code 0 if all PASS/WARN, 1 if any FAIL.
    """
    workspace = Path(config.workspace_root).resolve()

    all_results: list[DiagnosticResult] = []
    all_results.extend(check_python_environment())
    all_results.extend(check_dependencies())
    all_results.extend(check_cli_launcher())
    all_results.extend(check_local_model_services(config))
    all_results.extend(check_workspace_and_tools(workspace))

    total = len(all_results)
    passed = sum(1 for r in all_results if r.status == "PASS")
    warnings = sum(1 for r in all_results if r.status == "WARN")
    failed = sum(1 for r in all_results if r.status == "FAIL")

    if plain:
        print("=" * 60)
        print(f"CodeMind Doctor Diagnostics v{__version__}")
        print("=" * 60)
        current_cat = ""
        for r in all_results:
            if r.category != current_cat:
                current_cat = r.category
                print(f"\n[{current_cat}]")
            status_tag = "[OK]" if r.status == "PASS" else f"[{r.status}]"
            print(f"  {status_tag:7} {r.name:24} : {r.message}")
            if r.remediation:
                print(f"          Fix: {r.remediation}")

        print("\n" + "-" * 60)
        print(f"Summary: {passed} passed, {warnings} warning(s), {failed} failed out of {total} checks.")
        if failed > 0:
            print("Action required: Please resolve the failed checks above.")
            return 1
        return 0

    # Rich formatted output
    console = Console()
    console.print()
    console.print(
        Panel(
            Text.assemble(
                (f"{__brand_mark__} CodeMind Doctor Diagnostics\n", f"bold {COLOR_ACCENT}"),
                ("Comprehensive system, environment, and inference health check.", f"italic {COLOR_MUTED}"),
            ),
            border_style="cyan",
        )
    )

    table = Table(title="System Diagnostics", border_style="dim")
    table.add_column("Category", style="cyan", no_wrap=True)
    table.add_column("Check", style="bold")
    table.add_column("Status", justify="center", width=8)
    table.add_column("Details", style="dim")

    for r in all_results:
        if r.status == "PASS":
            status_cell = f"[{COLOR_SUCCESS}]✓ PASS[/]"
        elif r.status == "WARN":
            status_cell = f"[{COLOR_WARNING}]! WARN[/]"
        else:
            status_cell = f"[{COLOR_DANGER}]✗ FAIL[/]"

        table.add_row(r.category, r.name, status_cell, r.message)

    console.print(table)

    # Remediation hints if any
    remediations = [r for r in all_results if r.remediation and r.status in ("WARN", "FAIL")]
    if remediations:
        console.print("\n[bold yellow]Recommended Actions:[/bold yellow]")
        for r in remediations:
            console.print(f" • [bold]{r.name}[/bold]: {r.remediation}")

    console.print()
    if failed == 0:
        console.print(
            f"[{COLOR_SUCCESS}]✓ All core systems operational ({passed} passed, {warnings} warning(s)). Milo is ready to code![/{COLOR_SUCCESS}]\n"
        )
        return 0
    else:
        console.print(
            f"[{COLOR_DANGER}]✗ Diagnostics completed with {failed} failure(s). Please review the actions above.[/{COLOR_DANGER}]\n"
        )
        return 1
