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

    async def _check() -> None:
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
        git_dir = ws_path / ".git"
        if git_dir.is_dir():
            ui.print_info("Git repository: DETECTED")
        else:
            ui.print_info("Git repository: NOT INITIALIZED (non-git directory)")

        # Check .codemind state directory
        cm_dir = ws_path / ".codemind"
        if cm_dir.is_dir():
            ui.print_info(f"CodeMind workspace data: FOUND ({cm_dir})")
        else:
            ui.print_info("CodeMind workspace data: Clean (not yet configured)")

    asyncio.run(_check())


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

    from codemind.runtime.agent import CodeMindAgent

    agent = CodeMindAgent(config=config, ui=ui)
    await agent.initialize(resume_session_id=resume_session_id)
    await agent.run_task(prompt)


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

    from codemind.runtime.agent import CodeMindAgent

    agent = CodeMindAgent(config=config, ui=ui)
    await agent.initialize(resume_session_id=resume_session_id)

    prompt_symbol = "codemind> " if config.plain_mode else "▟●▙ > "
    interrupted_once = False

    while True:
        try:
            user_input = input(prompt_symbol).strip()
            interrupted_once = False

            if not user_input:
                continue

            cmd_lower = user_input.lower()

            if cmd_lower in ["exit", "quit", ":q"]:
                ui.print_info("Goodbye from Milo!")
                break

            if cmd_lower == "clear":
                os.system("clear")
                ui.print_banner(
                    model_name=config.model.model_name,
                    provider=config.model.provider.value,
                    workspace=config.workspace_root,
                    permission_mode=config.security.permission_mode.value,
                    turn_budget=config.runtime.max_turns,
                )
                continue

            if cmd_lower in ["continue", "resume", ":c"]:
                ui.print_info("Resuming paused task with a fresh turn budget...")
                await agent.resume_paused_task()
                continue

            if cmd_lower.startswith("budget "):
                parts = user_input.split()
                if len(parts) == 2 and parts[1].isdigit():
                    new_budget = int(parts[1])
                    config.runtime.max_turns = new_budget
                    ui.print_success(f"Turn budget updated to {new_budget} turns.")
                else:
                    ui.print_error("Usage: budget <number_of_turns>")
                continue

            if cmd_lower == "plan":
                if agent.active_state and agent.active_state.plan:
                    ui.print_plan(agent.active_state.plan.to_dict_list())
                elif agent.active_snapshot and agent.active_snapshot.plan:
                    ui.print_plan(agent.active_snapshot.plan)
                else:
                    ui.print_info("No active task plan found.")
                continue

            if cmd_lower == "status":
                turns = agent.active_snapshot.turns_completed if agent.active_snapshot else 0
                sess_id = agent.active_snapshot.session_id if agent.active_snapshot else "none"
                is_comp = agent.active_snapshot.is_completed if agent.active_snapshot else False
                ui.print_info(
                    f"Session: {sess_id} | Completed: {is_comp} | Cumulative Turns: {turns} | Current Budget: {config.runtime.max_turns}"
                )
                continue

            if cmd_lower in ["help", ":h", "?"]:
                if not config.plain_mode:
                    ui.console.print("\n[bold cyan]CodeMind Interactive Commands:[/bold cyan]")
                    ui.console.print("  [bold]continue / resume[/bold] : Continue a paused task with a fresh turn budget")
                    ui.console.print("  [bold]budget <n>[/bold]        : Update turn budget (e.g. 'budget 30')")
                    ui.console.print("  [bold]plan[/bold]              : Display the current structured task plan")
                    ui.console.print("  [bold]status[/bold]            : View session statistics and turn counts")
                    ui.console.print("  [bold]clear[/bold]             : Clear the terminal screen")
                    ui.console.print("  [bold]exit / quit[/bold]       : Exit the CodeMind companion\n")
                else:
                    print("\nCodeMind Interactive Commands:")
                    print("  continue / resume : Continue a paused task with a fresh turn budget")
                    print("  budget <n>        : Update turn budget (e.g. 'budget 30')")
                    print("  plan              : Display the current structured task plan")
                    print("  status            : View session statistics and turn counts")
                    print("  clear             : Clear the terminal screen")
                    print("  exit / quit       : Exit the CodeMind companion\n")
                continue

            # Execute task instruction
            await agent.run_task(user_input)

        except KeyboardInterrupt:
            if interrupted_once:
                ui.print_info("\nGoodbye from Milo!")
                break
            interrupted_once = True
            print("\nSession interrupted. Press Ctrl+C again or type 'exit' to quit.")
        except EOFError:
            ui.print_info("\nGoodbye from Milo!")
            break
