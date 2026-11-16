"""Main CLI entry points for CodeMind CLI using Typer and DefaultGroup."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import typer
import typer.core

from codemind import __brand_mark__, __mascot__, __product_name__, __version__
from codemind.cli.branding import BRAND_MARK, PLAIN_BRAND_MARK, TAGLINE
from codemind.cli.ui import TerminalUI
from codemind.config import CodeMindConfig, ModelProvider, PermissionMode


class CodeMindGroup(typer.core.TyperGroup):
    """Custom TyperGroup that routes any unmatched non-flag first argument to the 'ask' command."""

    def parse_args(self, ctx: typer.Context, args: list[str]) -> list[str]:
        if args and not args[0].startswith("-") and args[0] not in self.commands:
            args.insert(0, "ask")
        return super().parse_args(ctx, args)


app = typer.Typer(
    cls=CodeMindGroup,
    name="codemind",
    help=f"{BRAND_MARK} - {TAGLINE}",
    add_completion=False,
    invoke_without_command=True,
)

from codemind.cli.agents_cli import agents_app
from codemind.cli.connectors_cli import connectors_app
from codemind.cli.mcp_cli import mcp_app
from codemind.cli.memory_cli import memory_app
from codemind.cli.models_cli import models_app
from codemind.cli.sidecar_cli import sidecar_app
from codemind.cli.skills_cli import skills_app
from codemind.cli.task_cli import task_app

app.add_typer(models_app, name="models")
app.add_typer(memory_app, name="memory")
app.add_typer(skills_app, name="skills")
app.add_typer(task_app, name="task")
app.add_typer(agents_app, name="agents")
app.add_typer(sidecar_app, name="sidecar")
app.add_typer(connectors_app, name="connectors")
app.add_typer(mcp_app, name="mcp")


def version_callback(value: bool) -> None:
    if value:
        print(f"{BRAND_MARK} v{__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main_entry(
    ctx: typer.Context,
    resume: Optional[str] = typer.Option(
        None,
        "--resume",
        "-r",
        help="Resume an existing session by ID.",
    ),
    mode: Optional[str] = typer.Option(
        None,
        "--mode",
        "-m",
        help="Permission mode: supervised, read-only, or trusted.",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Target model identifier (e.g. codemind, qwen3.6:35b).",
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        "-p",
        help="Model provider: codemind-local, ollama, or mock.",
    ),
    endpoint: Optional[str] = typer.Option(
        None,
        "--endpoint",
        "-e",
        help="Local model serving endpoint URL.",
    ),
    max_turns: Optional[int] = typer.Option(
        None,
        "--max-turns",
        "-t",
        help="Maximum turn budget per task.",
    ),
    plain: bool = typer.Option(
        False,
        "--plain",
        "--no-color",
        help="Disable ANSI formatting, color, and animations.",
    ),
    workspace: Optional[str] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace root path (defaults to current directory).",
    ),
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show product version and exit.",
    ),
) -> None:
    """Primary execution entry point for CodeMind CLI."""
    if ctx.invoked_subcommand is not None:
        return

    # Build configuration with CLI overrides
    overrides: dict = {}
    if plain or os.getenv("NO_COLOR"):
        overrides["plain_mode"] = True
    if mode:
        overrides.setdefault("security", {})["permission_mode"] = mode
    if model:
        overrides.setdefault("model", {})["model_name"] = model
    if provider:
        overrides.setdefault("model", {})["provider"] = provider
    if endpoint:
        overrides.setdefault("model", {})["endpoint"] = endpoint
    if max_turns:
        overrides.setdefault("runtime", {})["max_turns"] = max_turns

    ws_path = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws_path, overrides=overrides)
    ui = TerminalUI(plain_mode=config.plain_mode)

    # Verify or start local model service safely
    from codemind.models.service_manager import ensure_model_service

    ok, msg = asyncio.run(ensure_model_service(config.model, ui=ui, auto_start=True))
    if not ok:
        ui.print_error(f"Local inference provider unavailable: {msg}")
        if not config.plain_mode:
            ui.console.print("\n[bold yellow]Remediation Options:[/bold yellow]")
            ui.console.print("  1. Start Ollama: [bold cyan]ollama serve[/bold cyan]")
            ui.console.print("  2. Run system diagnostics: [bold cyan]codemind doctor[/bold cyan]")
            ui.console.print("  3. Run offline mock mode: [bold cyan]codemind --provider mock[/bold cyan]\n")
        else:
            print("\nRemediation Options:")
            print("  1. Start Ollama: ollama serve")
            print("  2. Run system diagnostics: codemind doctor")
            print("  3. Run offline mock mode: codemind --provider mock\n")
        raise typer.Exit(code=1)

    # Launch interactive companion mode
    asyncio.run(run_interactive(config, ui, resume_session_id=resume))


@app.command(name="run")
def run_cmd(
    prompt: Optional[str] = typer.Argument(None, help="Prompt or task instruction (launches interactive mode if omitted)."),
    resume: Optional[str] = typer.Option(None, "--resume", "-r", help="Resume a session by ID."),
    max_turns: Optional[int] = typer.Option(None, "--max-turns", "-t", help="Maximum execution turns."),
    mode: Optional[str] = typer.Option(None, "--mode", "-m", help="Permission mode."),
    model: Optional[str] = typer.Option(None, "--model", help="Target model identifier."),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Model provider."),
    endpoint: Optional[str] = typer.Option(None, "--endpoint", "-e", help="Model serving endpoint URL."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Disable ANSI formatting."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root path."),
) -> None:
    """Execute a task instruction directly or launch interactive mode."""
    overrides: dict = {}
    if plain or os.getenv("NO_COLOR"):
        overrides["plain_mode"] = True
    if mode:
        overrides.setdefault("security", {})["permission_mode"] = mode
    if model:
        overrides.setdefault("model", {})["model_name"] = model
    if provider:
        overrides.setdefault("model", {})["provider"] = provider
    if endpoint:
        overrides.setdefault("model", {})["endpoint"] = endpoint
    if max_turns:
        overrides.setdefault("runtime", {})["max_turns"] = max_turns

    ws_path = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws_path, overrides=overrides)
    ui = TerminalUI(plain_mode=config.plain_mode)

    from codemind.models.service_manager import ensure_model_service

    ok, msg = asyncio.run(ensure_model_service(config.model, ui=ui, auto_start=True))
    if not ok:
        ui.print_error(f"Local inference provider unavailable: {msg}")
        raise typer.Exit(code=1)

    if prompt:
        asyncio.run(run_one_shot(prompt, config, ui, resume_session_id=resume))
    else:
        asyncio.run(run_interactive(config, ui, resume_session_id=resume))


@app.command(name="resume")
def resume_cmd(
    session_id: Optional[str] = typer.Argument(None, help="Session ID to resume (or latest active session if omitted)."),
    max_turns: Optional[int] = typer.Option(None, "--max-turns", "-t", help="Additional turns budget for continuation."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Disable ANSI formatting."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root path."),
) -> None:
    """Resume an existing or paused workflow session."""
    ws_path = Path(workspace or os.getcwd()).resolve()
    overrides: dict = {}
    if plain or os.getenv("NO_COLOR"):
        overrides["plain_mode"] = True
    if max_turns:
        overrides.setdefault("runtime", {})["max_turns"] = max_turns

    config = CodeMindConfig.load(workspace_dir=ws_path, overrides=overrides)
    ui = TerminalUI(plain_mode=config.plain_mode)

    # If no session_id given, scan latest checkpoint
    target_id = session_id
    if not target_id:
        from codemind.orchestration.checkpoint import CheckpointManager

        mgr = CheckpointManager(ws_path)
        matching = sorted(mgr.checkpoints_dir.glob("*_latest.json"), reverse=True)
        if matching:
            target_id = matching[0].stem.replace("_latest", "")

    if not target_id:
        ui.print_error("No existing session found to resume. Please provide a session ID.")
        raise typer.Exit(code=1)

    from codemind.models.service_manager import ensure_model_service

    ok, msg = asyncio.run(ensure_model_service(config.model, ui=ui, auto_start=True))
    if not ok:
        ui.print_error(f"Local inference provider unavailable: {msg}")
        raise typer.Exit(code=1)

    asyncio.run(run_interactive(config, ui, resume_session_id=target_id))


@app.command(name="ask", hidden=True)
def ask_cmd(
    prompt: str = typer.Argument(..., help="Prompt or task instruction"),
    resume: Optional[str] = typer.Option(None, "--resume", "-r"),
    mode: Optional[str] = typer.Option(None, "--mode", "-m"),
    model: Optional[str] = typer.Option(None, "--model"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p"),
    endpoint: Optional[str] = typer.Option(None, "--endpoint", "-e"),
    max_turns: Optional[int] = typer.Option(None, "--max-turns", "-t"),
    plain: bool = typer.Option(False, "--plain", "--no-color"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
) -> None:
    """One-shot command execution."""
    overrides: dict = {}
    if plain or os.getenv("NO_COLOR"):
        overrides["plain_mode"] = True
    if mode:
        overrides.setdefault("security", {})["permission_mode"] = mode
    if model:
        overrides.setdefault("model", {})["model_name"] = model
    if provider:
        overrides.setdefault("model", {})["provider"] = provider
    if endpoint:
        overrides.setdefault("model", {})["endpoint"] = endpoint
    if max_turns:
        overrides.setdefault("runtime", {})["max_turns"] = max_turns

    ws_path = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws_path, overrides=overrides)
    ui = TerminalUI(plain_mode=config.plain_mode)

    from codemind.models.service_manager import ensure_model_service

    ok, msg = asyncio.run(ensure_model_service(config.model, ui=ui, auto_start=True))
    if not ok:
        ui.print_error(f"Local inference provider unavailable: {msg}")
        raise typer.Exit(code=1)

    asyncio.run(run_one_shot(prompt, config, ui, resume_session_id=resume))


@app.command(name="doctor")
def doctor_cmd(
    plain: bool = typer.Option(
        False,
        "--plain",
        "--no-color",
        help="Disable ANSI colors and formatting.",
    ),
    workspace: Optional[str] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Target workspace root path.",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Target model identifier.",
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        "-p",
        help="Model provider (codemind-local, ollama, mock).",
    ),
    endpoint: Optional[str] = typer.Option(
        None,
        "--endpoint",
        "-e",
        help="Model serving endpoint URL.",
    ),
) -> None:
    """Run comprehensive diagnostics on environment, dependencies, and local model."""
    from codemind.cli.doctor import run_doctor

    ws_path = Path(workspace or os.getcwd()).resolve()
    overrides: dict = {}
    if plain or os.getenv("NO_COLOR"):
        overrides["plain_mode"] = True
    if model:
        overrides.setdefault("model", {})["model_name"] = model
    if provider:
        overrides.setdefault("model", {})["provider"] = provider
    if endpoint:
        overrides.setdefault("model", {})["endpoint"] = endpoint

    config = CodeMindConfig.load(workspace_dir=ws_path, overrides=overrides)
    code = run_doctor(config, plain=config.plain_mode)
    if code != 0:
        raise typer.Exit(code=code)


@app.command(name="install")
def install_cmd(
    bin_dir: Optional[str] = typer.Option(
        None,
        "--bin-dir",
        help="Custom directory for global launcher executable (defaults to ~/.local/bin).",
    ),
    venv_path: Optional[str] = typer.Option(
        None,
        "--venv",
        help="Custom path for virtual environment (defaults to repo .venv).",
    ),
    plain: bool = typer.Option(
        False,
        "--plain",
        "--no-color",
        help="Disable ANSI formatting.",
    ),
) -> None:
    """Install or update the global CodeMind CLI launcher."""
    from codemind.cli.install_cmd import run_install

    target_bin = Path(bin_dir).resolve() if bin_dir else None
    target_venv = Path(venv_path).resolve() if venv_path else None
    code = run_install(user_bin_dir=target_bin, venv_dir=target_venv, plain=plain)
    if code != 0:
        raise typer.Exit(code=code)


@app.command(name="status")
def status_cmd(
    plain: bool = typer.Option(
        False,
        "--plain",
        "--no-color",
        help="Disable ANSI colors.",
    ),
    workspace: Optional[str] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Target workspace root.",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Target model identifier.",
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        "-p",
        help="Model provider (codemind-local, ollama, mock).",
    ),
    endpoint: Optional[str] = typer.Option(
        None,
        "--endpoint",
        "-e",
        help="Model serving endpoint URL.",
    ),
) -> None:
    """Inspect environment, local model connectivity, and workspace health."""
    ws_path = Path(workspace or os.getcwd()).resolve()
    overrides: dict = {"plain_mode": plain}
    if model:
        overrides.setdefault("model", {})["model_name"] = model
    if provider:
        overrides.setdefault("model", {})["provider"] = provider
    if endpoint:
        overrides.setdefault("model", {})["endpoint"] = endpoint

    config = CodeMindConfig.load(workspace_dir=ws_path, overrides=overrides)
    ui = TerminalUI(plain_mode=config.plain_mode)

    ui.print_banner(
        model_name=config.model.model_name,
        provider=config.model.provider.value,
        workspace=config.workspace_root,
        permission_mode=config.security.permission_mode.value,
        turn_budget=config.runtime.max_turns,
    )

    asyncio.run(run_doctor_checks(config, ui))


async def run_doctor_checks(config: CodeMindConfig, ui: TerminalUI) -> None:
    """Run health, model connectivity, git, and workspace diagnostics."""
    from codemind.models import create_adapter

    ui.print_info(f"Checking model connectivity at {config.model.endpoint}...")
    try:
        adapter = create_adapter(config.model)
        health = await adapter.check_health()
        if health.healthy:
            ui.print_info(f"Model status: HEALTHY ({health.details.get('message', 'Ready')})")
        else:
            ui.print_error(f"Model unreachable: {health.error or 'Connection refused'}")
    except Exception as ex:
        ui.print_error(f"Failed to initialize model adapter: {ex}")

    # Check git status in workspace
    ws_root = Path(config.workspace_root)
    git_dir = ws_root / ".git"
    if git_dir.is_dir():
        ui.print_info("Git repository: DETECTED")
    else:
        ui.print_info("Git repository: NOT INITIALIZED (non-git directory)")

    # Check .codemind state directory
    cm_dir = ws_root / ".codemind"
    if cm_dir.is_dir():
        ui.print_info(f"CodeMind workspace data: FOUND ({cm_dir})")
    else:
        ui.print_info("CodeMind workspace data: Clean (not yet configured)")


async def handle_slash_command(
    raw_input: str,
    agent: Any,
    config: CodeMindConfig,
    ui: TerminalUI,
) -> tuple[bool, bool]:
    """Handle slash commands and CLI management directives.

    Returns (handled, should_exit).
    """
    cmd = raw_input.strip()
    cmd_lower = cmd.lower()

    if cmd_lower in ["/exit", "exit", "/quit", "quit", ":q"]:
        ui.print_info("Goodbye from Milo!")
        return True, True

    if cmd_lower in ["/clear", "clear"]:
        os.system("clear")
        ui.print_banner(
            model_name=config.model.model_name,
            provider=config.model.provider.value,
            workspace=config.workspace_root,
            permission_mode=config.security.permission_mode.value,
            turn_budget=config.runtime.max_turns,
        )
        return True, False

    if cmd_lower in ["/help", "help", ":h", "?"]:
        from codemind.cli.repl import SLASH_COMMANDS

        if not config.plain_mode:
            ui.console.print("\n[bold cyan]CodeMind Slash Commands & Controls:[/bold cyan]")
            for sc_name, sc_desc in SLASH_COMMANDS:
                ui.console.print(f"  [bold green]{sc_name:12}[/bold green] : {sc_desc}")
            ui.console.print("\n[bold cyan]Context Injection & Ergonomics:[/bold cyan]")
            ui.console.print("  [bold yellow]@path/to/file[/bold yellow] : Mention workspace files in prompts to inject bounded context (up to 10KB/200L)")
            ui.console.print("  [bold yellow]budget <n>[/bold yellow]    : Adjust the execution turn budget dynamically (e.g. 'budget 30')")
            ui.console.print("  [bold yellow]Ctrl+C[/bold yellow]        : Interrupt current running task or cancel prompt")
            ui.console.print("  [bold yellow]Ctrl+D[/bold yellow]        : Exit CodeMind companion session\n")
        else:
            print("\nCodeMind Slash Commands & Controls:")
            for sc_name, sc_desc in SLASH_COMMANDS:
                print(f"  {sc_name:12} : {sc_desc}")
            print("\nContext Injection & Ergonomics:")
            print("  @path/to/file : Mention workspace files in prompts to inject bounded context")
            print("  budget <n>    : Adjust the execution turn budget dynamically")
            print("  Ctrl+C        : Interrupt current running task or cancel prompt")
            print("  Ctrl+D        : Exit CodeMind companion session\n")
        return True, False

    if cmd_lower in ["/status", "status"]:
        turns = agent.active_snapshot.turns_completed if agent.active_snapshot else 0
        sess_id = agent.active_snapshot.session_id if agent.active_snapshot else "none"
        is_comp = agent.active_snapshot.is_completed if agent.active_snapshot else False
        files_cnt = len(agent.active_snapshot.files_changed) if agent.active_snapshot else 0
        if not config.plain_mode:
            ui.console.print("\n[bold cyan]CodeMind Session Status:[/bold cyan]")
            ui.console.print(f"  Session ID    : [bold]{sess_id}[/bold]")
            ui.console.print(f"  Completed     : [{'green' if is_comp else 'yellow'}]{is_comp}[/{'green' if is_comp else 'yellow'}]")
            ui.console.print(f"  Turns Used    : {turns}")
            ui.console.print(f"  Active Budget : {config.runtime.max_turns} turns")
            ui.console.print(f"  Model         : {config.model.model_name} ({config.model.provider.value})")
            ui.console.print(f"  Endpoint      : {config.model.endpoint}")
            ui.console.print(f"  Permission    : {config.security.permission_mode.value}")
            ui.console.print(f"  Files Changed : {files_cnt}\n")
        else:
            print("\nCodeMind Session Status:")
            print(f"  Session ID    : {sess_id}")
            print(f"  Completed     : {is_comp}")
            print(f"  Turns Used    : {turns}")
            print(f"  Active Budget : {config.runtime.max_turns} turns")
            print(f"  Model         : {config.model.model_name} ({config.model.provider.value})")
            print(f"  Endpoint      : {config.model.endpoint}")
            print(f"  Permission    : {config.security.permission_mode.value}")
            print(f"  Files Changed : {files_cnt}\n")
        return True, False

    if cmd_lower in ["/doctor", "doctor"]:
        await run_doctor_checks(config, ui)
        return True, False

    if cmd_lower in ["/models", "models"]:
        from codemind.models import create_adapter

        adapter = create_adapter(config.model)
        health = await adapter.check_health()
        health_str = "HEALTHY" if health.healthy else f"UNREACHABLE ({health.error})"
        if not config.plain_mode:
            ui.console.print("\n[bold cyan]CodeMind Model Gateway & Privacy:[/bold cyan]")
            ui.console.print(f"  Active Provider : [bold]{config.model.provider.value}[/bold]")
            ui.console.print(f"  Active Model    : [bold]{config.model.model_name}[/bold]")
            ui.console.print(f"  Endpoint        : {config.model.endpoint}")
            ui.console.print(f"  Gateway Health  : [{'green' if health.healthy else 'red'}]{health_str}[/{'green' if health.healthy else 'red'}]")
            ui.console.print("  Privacy Policy  : [bold green]LOCAL-ONLY ENFORCED[/bold green] (Zero cloud egress, no telemetry)")
            ui.console.print("  Supported       : codemind-local, ollama, mock\n")
        else:
            print("\nCodeMind Model Gateway & Privacy:")
            print(f"  Active Provider : {config.model.provider.value}")
            print(f"  Active Model    : {config.model.model_name}")
            print(f"  Endpoint        : {config.model.endpoint}")
            print(f"  Gateway Health  : {health_str}")
            print("  Privacy Policy  : LOCAL-ONLY ENFORCED (Zero cloud egress, no telemetry)")
            print("  Supported       : codemind-local, ollama, mock\n")
        return True, False

    if cmd_lower in ["/memory", "memory"]:
        stats = agent.memory.get_stats()
        if not config.plain_mode:
            ui.console.print("\n[bold cyan]CodeMind SQLite Project Memory:[/bold cyan]")
            ui.console.print(f"  Database Path   : {stats.db_path}")
            ui.console.print(f"  Database Size   : {stats.db_size_bytes} bytes")
            ui.console.print(f"  Total Entries   : [bold]{stats.total_entries}[/bold]")
            if stats.by_layer:
                ui.console.print("  Entries by Layer:")
                for layer, count in stats.by_layer.items():
                    ui.console.print(f"    - {layer}: {count}")
            if stats.total_entries == 0:
                ui.console.print("  [dim]Project memory is initialized and ready for automated knowledge distillation.[/dim]\n")
            else:
                ui.console.print("")
        else:
            print("\nCodeMind SQLite Project Memory:")
            print(f"  Database Path   : {stats.db_path}")
            print(f"  Database Size   : {stats.db_size_bytes} bytes")
            print(f"  Total Entries   : {stats.total_entries}")
            if stats.by_layer:
                print("  Entries by Layer:")
                for layer, count in stats.by_layer.items():
                    print(f"    - {layer}: {count}")
            print("")
        return True, False

    if cmd_lower in ["/skills", "skills"]:
        skills = agent.skills.discover_all()
        if not config.plain_mode:
            ui.console.print("\n[bold cyan]CodeMind Engineering Skills Registry:[/bold cyan]")
            for s in skills:
                status = "[green]ENABLED[/green]" if s.enabled else "[red]DISABLED[/red]"
                ui.console.print(f"  - [bold]{s.name}[/bold] (v{s.version}) [{status}]: {s.description}")
            ui.console.print("")
        else:
            print("\nCodeMind Engineering Skills Registry:")
            for s in skills:
                status = "ENABLED" if s.enabled else "DISABLED"
                print(f"  - {s.name} (v{s.version}) [{status}]: {s.description}")
            print("")
        return True, False

    if cmd_lower in ["/agents", "agents"]:
        if not config.plain_mode:
            ui.console.print("\n[bold cyan]CodeMind Multi-Agent Orchestration Architecture:[/bold cyan]")
            ui.console.print("  Runtime Architecture : Sidecar Worker Sandboxes (.codemind/workspaces/)")
            ui.console.print("  VRAM Safety Policy   : Sequential Inference Gate (1 active GPU inference at a time)")
            ui.console.print("  Available Roles      :")
            ui.console.print("    - [bold yellow]coordinator[/bold yellow] : Architecture synthesis, planning, and peer-review")
            ui.console.print("    - [bold yellow]research[/bold yellow]    : Read-only codebase indexing and discovery")
            ui.console.print("    - [bold yellow]coding[/bold yellow]      : File modifications, diff generation, implementation")
            ui.console.print("    - [bold yellow]debugging[/bold yellow]   : Fault isolation, stack trace diagnostics, root-cause fixes")
            ui.console.print("    - [bold yellow]testing[/bold yellow]     : Hermetic test authoring and test execution")
            ui.console.print("  Status               : [bold green]READY[/bold green]\n")
        else:
            print("\nCodeMind Multi-Agent Orchestration Architecture:")
            print("  Runtime Architecture : Sidecar Worker Sandboxes (.codemind/workspaces/)")
            print("  VRAM Safety Policy   : Sequential Inference Gate (1 active GPU inference at a time)")
            print("  Available Roles      :")
            print("    - coordinator : Architecture synthesis, planning, and peer-review")
            print("    - research    : Read-only codebase indexing and discovery")
            print("    - coding      : File modifications, diff generation, implementation")
            print("    - debugging   : Fault isolation, stack trace diagnostics, root-cause fixes")
            print("    - testing     : Hermetic test authoring and test execution")
            print("  Status               : READY\n")
        return True, False

    if cmd_lower in ["/task", "task", "/plan", "plan"]:
        if agent.active_state and agent.active_state.plan:
            ui.print_plan(agent.active_state.plan.to_dict_list())
        elif agent.active_snapshot and agent.active_snapshot.plan:
            ui.print_plan(agent.active_snapshot.plan)
        else:
            ui.print_info("No active task plan found.")
        return True, False

    if cmd_lower in ["/diff", "diff"]:
        import subprocess

        try:
            res_status = subprocess.run(
                ["git", "status", "--short"],
                cwd=config.workspace_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            res_diff = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=config.workspace_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            status_out = res_status.stdout.strip()
            diff_out = res_diff.stdout.strip()
            if not status_out and not diff_out:
                ui.print_info("Working tree clean. No uncommitted modifications.")
            else:
                if status_out:
                    ui.print_info(f"Uncommitted Files:\n{status_out}")
                if diff_out:
                    ui.print_info(f"Diff Summary:\n{diff_out}")
        except Exception as ex:
            ui.print_warning(f"Unable to read git diff: {ex}")
        return True, False

    if cmd_lower in ["/mcp", "mcp"] or cmd_lower.startswith("/mcp ") or cmd_lower.startswith("mcp "):
        parts = cmd.split()
        sub = parts[1].lower() if len(parts) > 1 else "list"

        if sub == "list":
            servers = agent.mcp.list_servers() if hasattr(agent, "mcp") else []
            if not config.plain_mode:
                ui.console.print("\n[bold cyan]Model Context Protocol (MCP) Servers:[/bold cyan]")
                if not servers:
                    ui.console.print("  [dim]No MCP servers configured in .codemind/mcp.json[/dim]\n")
                else:
                    for s in servers:
                        st = "[red]DISABLED[/red]" if s["disabled"] else ("[green]RUNNING[/green]" if s["is_running"] else "[yellow]CONFIGURED[/yellow]")
                        ui.console.print(f"  - [bold]{s['name']}[/bold] [{st}]: {s['command']} {' '.join(s['args'])}")
                        if s["tools"]:
                            ui.console.print(f"    Tools ({s['tool_count']}): {', '.join(s['tools'])}")
                    ui.console.print("")
            else:
                print("\nModel Context Protocol (MCP) Servers:")
                if not servers:
                    print("  No MCP servers configured in .codemind/mcp.json\n")
                else:
                    for s in servers:
                        st = "DISABLED" if s["disabled"] else ("RUNNING" if s["is_running"] else "CONFIGURED")
                        print(f"  - {s['name']} [{st}]: {s['command']} {' '.join(s['args'])}")
                        if s["tools"]:
                            print(f"    Tools ({s['tool_count']}): {', '.join(s['tools'])}")
                    print("")
            return True, False

        if sub == "disable" and len(parts) >= 3:
            s_name = parts[2]
            ok = agent.mcp.disable_server(s_name) if hasattr(agent, "mcp") else False
            if ok:
                ui.print_success(f"MCP server '{s_name}' disabled.")
            else:
                ui.print_error(f"MCP server '{s_name}' not found.")
            return True, False

        if sub == "enable" and len(parts) >= 3:
            s_name = parts[2]
            ok = agent.mcp.enable_server(s_name) if hasattr(agent, "mcp") else False
            if ok:
                ui.print_success(f"MCP server '{s_name}' enabled.")
            else:
                ui.print_error(f"MCP server '{s_name}' not found.")
            return True, False

        if sub == "remove" and len(parts) >= 3:
            s_name = parts[2]
            ok = agent.mcp.remove_server(s_name) if hasattr(agent, "mcp") else False
            if ok:
                ui.print_success(f"MCP server '{s_name}' removed.")
            else:
                ui.print_error(f"MCP server '{s_name}' not found.")
            return True, False

        if sub == "add" and len(parts) >= 4:
            s_name = parts[2]
            s_cmd = parts[3]
            s_args = parts[4:] if len(parts) > 4 else []
            if hasattr(agent, "mcp"):
                agent.mcp.add_server(name=s_name, command=s_cmd, args=s_args)
                ui.print_success(f"MCP server '{s_name}' configured in .codemind/mcp.json.")
            return True, False

        ui.print_error("Usage: /mcp [list | add <name> <cmd> [args...] | disable <name> | enable <name> | remove <name>]")
        return True, False

    if cmd_lower in ["/connectors", "connectors"] or cmd_lower.startswith("/connectors ") or cmd_lower.startswith("connectors "):
        parts = cmd.split()
        sub = parts[1].lower() if len(parts) > 1 else "status"

        if hasattr(agent, "connectors"):
            if sub in ("list", "status"):
                statuses = agent.connectors.get_all_statuses()
                if not config.plain_mode:
                    ui.console.print("\n[bold cyan]CodeMind Universal Application Connectors:[/bold cyan]")
                    for s in statuses:
                        stat = s["status"]
                        stat_color = "green" if stat == "connected" else ("yellow" if stat == "expired" else "dim")
                        ui.console.print(f"  {s['icon']} [bold]{s['connector_id']:<16}[/bold] [{stat_color}]{stat.upper()}[/{stat_color}] ({s['category']}) - {s['actions_count']} actions")
                    ui.console.print("  [dim]Manage with 'codemind connectors' or 'codemind connectors inspect <id>'[/dim]\n")
                else:
                    print("\nCodeMind Universal Application Connectors:")
                    for s in statuses:
                        print(f"  {s['icon']} {s['connector_id']:<16} {s['status'].upper()} ({s['category']}) - {s['actions_count']} actions")
                    print()
                return True, False
            elif sub == "test" and len(parts) >= 3:
                c_id = parts[2]
                ui.print_info(f"Testing connector '{c_id}'...")
                health = await agent.connectors.test_connection(c_id)
                if health.healthy:
                    ui.print_success(f"Connector '{c_id}': {health.message} ({health.latency_ms} ms)")
                else:
                    ui.print_error(f"Connector '{c_id}': {health.message}")
                return True, False

        ui.print_info("Usage: /connectors [list | status | test <connector_id>]")
        return True, False

    if cmd_lower in ["/permissions", "permissions", "/policy", "policy"]:
        mode_str = config.security.permission_mode.value
        policy = getattr(agent.permission_checker, "policy", None)
        rules = policy.rules if policy else []

        if not config.plain_mode:
            ui.console.print("\n[bold cyan]CodeMind Security Permissions & Policies:[/bold cyan]")
            ui.console.print(f"  Base Mode: [bold green]{mode_str}[/bold green]")
            if rules:
                ui.console.print(f"  Declarative Policy Rules ({len(rules)} active):")
                for idx, r in enumerate(rules, 1):
                    dec_color = "green" if r.decision.value == "allow" else ("red" if r.decision.value == "deny" else "yellow")
                    match_desc = []
                    if r.tool:
                        match_desc.append(f"tool={r.tool}")
                    if r.command_prefix:
                        match_desc.append(f"cmd_prefix={' '.join(r.command_prefix)}")
                    if r.path_pattern:
                        match_desc.append(f"path={r.path_pattern}")
                    ui.console.print(f"    {idx}. [{dec_color}]{r.decision.value.upper()}[/{dec_color}] -> {', '.join(match_desc)}")
            else:
                ui.console.print("  [dim]No custom policy overrides in .codemind/permissions.yaml. Standard mode applies.[/dim]")
            ui.console.print("")
        else:
            print("\nCodeMind Security Permissions & Policies:")
            print(f"  Base Mode: {mode_str}")
            if rules:
                print(f"  Declarative Policy Rules ({len(rules)} active):")
                for idx, r in enumerate(rules, 1):
                    match_desc = []
                    if r.tool:
                        match_desc.append(f"tool={r.tool}")
                    if r.command_prefix:
                        match_desc.append(f"cmd_prefix={' '.join(r.command_prefix)}")
                    if r.path_pattern:
                        match_desc.append(f"path={r.path_pattern}")
                    print(f"    {idx}. {r.decision.value.upper()} -> {', '.join(match_desc)}")
            else:
                print("  No custom policy overrides in .codemind/permissions.yaml. Standard mode applies.")
            print("")
        return True, False

    if cmd_lower in ["/compact", "compact"]:
        if agent.active_state and agent.active_state.messages:
            from codemind.context.compactor import ContextCompactor

            compactor = ContextCompactor()
            res = compactor.compact(
                messages=agent.active_state.messages,
                task_plan=agent.active_state.plan,
                force=True,
            )
            if res.was_compacted:
                agent.active_state.messages = res.messages
                ui.print_success(
                    f"Context successfully compacted. Saved {res.saved_chars} characters ({res.original_chars} -> {res.compacted_chars})."
                )
            else:
                ui.print_info(f"Context does not require compaction ({res.original_chars} characters).")
        else:
            ui.print_info("No active conversation messages to compact.")
        return True, False

    if cmd_lower in ["/resume", "resume", "/continue", "continue", ":c"]:
        ui.print_info("Resuming paused task with a fresh turn budget...")
        await agent.resume_paused_task()
        return True, False

    if cmd_lower.startswith("budget ") or cmd_lower.startswith("/budget "):
        parts = cmd.split()
        if len(parts) == 2 and parts[1].isdigit():
            new_budget = int(parts[1])
            config.runtime.max_turns = new_budget
            ui.print_success(f"Turn budget updated to {new_budget} turns.")
        else:
            ui.print_error("Usage: /budget <number_of_turns>")
        return True, False

    return False, False


async def run_one_shot(
    prompt: str,
    config: CodeMindConfig,
    ui: TerminalUI,
    resume_session_id: str | None = None,
) -> None:
    """Execute a single-turn or bounded one-shot instruction."""
    ui.print_banner(
        model_name=config.model.model_name,
        provider=config.model.provider.value,
        workspace=config.workspace_root,
        permission_mode=config.security.permission_mode.value,
        turn_budget=config.runtime.max_turns,
    )
    ui.print_info(f"Executing instruction: '{prompt}'")

    from codemind.context.mentions import FileMentionProcessor
    from codemind.runtime.agent import CodeMindAgent

    agent = CodeMindAgent(config=config, ui=ui)
    await agent.initialize(resume_session_id=resume_session_id)

    # Process @file mentions in one-shot prompt
    mention_processor = FileMentionProcessor(config.workspace_root)
    augmented_prompt, mentions = mention_processor.process_mentions(prompt)
    if mentions:
        valid_mentions = [m for m in mentions if not m.warning]
        warn_mentions = [m for m in mentions if m.warning]
        if valid_mentions:
            ui.print_info(
                f"Loaded context for {len(valid_mentions)} mentioned file(s): "
                + ", ".join(f"@{m.rel_path} ({m.line_count}L)" for m in valid_mentions)
            )
        for m in warn_mentions:
            ui.print_warning(f"@{m.rel_path}: {m.warning}")

    await agent.run_task(augmented_prompt)


async def run_interactive(
    config: CodeMindConfig,
    ui: TerminalUI,
    resume_session_id: str | None = None,
) -> None:
    """Run interactive REPL companion loop with Milo."""
    ui.print_banner(
        model_name=config.model.model_name,
        provider=config.model.provider.value,
        workspace=config.workspace_root,
        permission_mode=config.security.permission_mode.value,
        turn_budget=config.runtime.max_turns,
    )

    from codemind.cli.repl import CodeMindInteractiveSession
    from codemind.context.mentions import FileMentionProcessor
    from codemind.runtime.agent import CodeMindAgent

    agent = CodeMindAgent(config=config, ui=ui)
    await agent.initialize(resume_session_id=resume_session_id)

    session = CodeMindInteractiveSession(
        workspace_root=config.workspace_root,
        plain_mode=config.plain_mode,
    )
    mention_processor = FileMentionProcessor(config.workspace_root)
    interrupted_once = False

    while True:
        try:
            user_input = session.prompt()
            interrupted_once = False

            if not user_input:
                continue

            handled, should_exit = await handle_slash_command(user_input, agent, config, ui)
            if should_exit:
                break
            if handled:
                continue

            # Process @file mentions in prompt
            augmented_prompt, mentions = mention_processor.process_mentions(user_input)
            if mentions:
                valid_mentions = [m for m in mentions if not m.warning]
                warn_mentions = [m for m in mentions if m.warning]
                if valid_mentions:
                    ui.print_info(
                        f"Loaded context for {len(valid_mentions)} mentioned file(s): "
                        + ", ".join(f"@{m.rel_path} ({m.line_count}L)" for m in valid_mentions)
                    )
                for m in warn_mentions:
                    ui.print_warning(f"@{m.rel_path}: {m.warning}")

            # Execute task instruction
            await agent.run_task(augmented_prompt)

        except KeyboardInterrupt:
            if interrupted_once:
                ui.print_info("\nGoodbye from Milo!")
                break
            interrupted_once = True
            print("\nSession interrupted. Press Ctrl+C again or type '/exit' to quit.")
        except EOFError:
            ui.print_info("\nGoodbye from Milo!")
            break
