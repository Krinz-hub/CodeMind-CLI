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

from codemind.cli.models_cli import models_app

app.add_typer(models_app, name="models")


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

    ws_path = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws_path, overrides=overrides)
    ui = TerminalUI(plain_mode=config.plain_mode)

    # Launch interactive companion mode
    asyncio.run(run_interactive(config, ui, resume_session_id=resume))


@app.command(name="ask", hidden=True)
def ask_cmd(
    prompt: str = typer.Argument(..., help="Prompt or task instruction"),
    resume: Optional[str] = typer.Option(None, "--resume", "-r"),
    mode: Optional[str] = typer.Option(None, "--mode", "-m"),
    model: Optional[str] = typer.Option(None, "--model"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p"),
    endpoint: Optional[str] = typer.Option(None, "--endpoint", "-e"),
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

    ws_path = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws_path, overrides=overrides)
    ui = TerminalUI(plain_mode=config.plain_mode)

    asyncio.run(run_one_shot(prompt, config, ui, resume_session_id=resume))


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
    """Run interactive REPL loop with Milo."""
    ui.print_banner(
        model_name=config.model.model_name,
        provider=config.model.provider.value,
        workspace=config.workspace_root,
        permission_mode=config.security.permission_mode.value,
    )

    from codemind.runtime.agent import CodeMindAgent

    agent = CodeMindAgent(config=config, ui=ui)
    await agent.initialize(resume_session_id=resume_session_id)

    prompt_symbol = "codemind> " if config.plain_mode else "▟●▙ > "

    while True:
        try:
            user_input = input(prompt_symbol).strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", ":q"]:
                ui.print_info("Goodbye from Milo!")
                break
            if user_input.lower() == "clear":
                os.system("clear")
                continue

            await agent.run_task(user_input)

        except (KeyboardInterrupt, EOFError):
            print("\nSession interrupted.")
            break
