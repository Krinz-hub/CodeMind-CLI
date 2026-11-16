"""CLI commands for discovering, testing, switching, and inspecting local models."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from codemind.cli.branding import COLOR_ACCENT, COLOR_DANGER, COLOR_INFO, COLOR_MUTED, COLOR_SUCCESS, COLOR_WARNING
from codemind.cli.ui import TerminalUI
from codemind.config import CodeMindConfig, ModelProvider, ModelSettings
from codemind.models import create_adapter
from codemind.models.discovery import DiscoveredModel, ModelDiscovery
from codemind.models.evaluator import ModelCapabilityTester

models_app = typer.Typer(
    name="models",
    help="Discover, switch, test, and inspect local intelligence models.",
    invoke_without_command=True,
)


@models_app.callback(invoke_without_command=True)
def models_default(
    ctx: typer.Context,
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Default handler for 'codemind models' - lists available models."""
    if ctx.invoked_subcommand is None:
        list_cmd(plain=plain, workspace=workspace)


@models_app.command(name="list")
def list_cmd(
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Display discovered local models from Ollama and OpenAI-compatible endpoints."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)

    async def _run() -> None:
        ui.print_info("Discovering local models from installed inference services...")
        models: list[DiscoveredModel] = await ModelDiscovery.discover_all(config)

        if not models:
            ui.print_error("No local models discovered. Ensure Ollama (127.0.0.1:11434) is running.")
            return

        if config.plain_mode:
            print("\nAvailable Local Models:")
            print(f"{'STATUS':<10} {'PROVIDER':<14} {'NAME':<30} {'PARAMS':<10} {'SIZE':<10}")
            print("-" * 78)
            for m in models:
                status_tag = "[ACTIVE]" if m.is_active else "[READY]"
                size_str = f"{m.size_gb} GB" if m.size_gb else "-"
                param_str = m.parameter_size or "-"
                print(f"{status_tag:<10} {m.provider:<14} {m.name:<30} {param_str:<10} {size_str:<10}")
            print()
            return

        table = Table(
            title="[bold #FF9E3B]Discovered Local Models[/bold #FF9E3B]",
            show_header=True,
            header_style="bold cyan",
            border_style=COLOR_MUTED,
        )
        table.add_column("Status", width=12, justify="center")
        table.add_column("Model Name", style="bold white")
        table.add_column("Provider", style="cyan")
        table.add_column("Parameters", style="green")
        table.add_column("Quantization", style="dim")
        table.add_column("Disk Size", style="dim white")

        for m in models:
            if m.is_active:
                status_cell = f"[{COLOR_ACCENT}]● ACTIVE[/{COLOR_ACCENT}]"
            else:
                status_cell = f"[{COLOR_SUCCESS}]✓ Ready[/{COLOR_SUCCESS}]"

            size_str = f"{m.size_gb} GB" if m.size_gb else "-"
            param_str = m.parameter_size or "-"
            quant_str = m.quantization or "-"

            table.add_row(
                status_cell,
                m.name,
                m.provider,
                param_str,
                quant_str,
                size_str,
            )

        ui.console.print(table)
        ui.console.print(f"[dim]Switch models anytime using: [bold]codemind models use <model>[/bold][/dim]\n")

    asyncio.run(_run())


@models_app.command(name="current")
def current_cmd(
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Show the currently active model and configuration."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)

    if config.plain_mode:
        print("\nActive Model Configuration:")
        print(f"  Model:            {config.model.model_name}")
        print(f"  Provider:         {config.model.provider.value}")
        print(f"  Endpoint:         {config.model.endpoint}")
        print(f"  Timeout:          {config.model.timeout_seconds}s")
        print(f"  Context:          {config.model.context_window} tokens")
        print(f"  Temperature:      {config.model.temperature}")
        if config.model.enable_fallback and config.model.fallback_model:
            fb_prov = config.model.fallback_provider.value if config.model.fallback_provider else "none"
            print(f"  Fallback Model:   {config.model.fallback_model} ({fb_prov})\n")
        else:
            print("  Fallback:         Disabled\n")
        return

    content = Text()
    content.append("Model Name:       ", style="bold")
    content.append(f"{config.model.model_name}\n", style=f"bold {COLOR_ACCENT}")
    content.append("Provider:         ", style="bold")
    content.append(f"{config.model.provider.value}\n", style=COLOR_INFO)
    content.append("Endpoint:         ", style="bold")
    content.append(f"{config.model.endpoint}\n", style="cyan")
    content.append("Timeout:          ", style="bold")
    content.append(f"{config.model.timeout_seconds} seconds\n", style="dim")
    content.append("Context Size:     ", style="bold")
    content.append(f"{config.model.context_window} tokens\n", style="dim")
    content.append("Temperature:      ", style="bold")
    content.append(f"{config.model.temperature}\n", style="dim")
    content.append("Fallback System:  ", style="bold")
    if config.model.enable_fallback and config.model.fallback_model:
        fb_prov = config.model.fallback_provider.value if config.model.fallback_provider else "none"
        content.append(f"Enabled -> {config.model.fallback_model} ({fb_prov})", style=COLOR_SUCCESS)
    else:
        content.append("Disabled", style=COLOR_WARNING)

    panel = Panel(
        content,
        title="[bold #FF9E3B]Active Intelligence Provider[/bold #FF9E3B]",
        border_style=COLOR_ACCENT,
        padding=(1, 2),
    )
    ui.console.print(panel)


@models_app.command(name="status")
def status_cmd(
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Test connection health of the currently active model."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)

    async def _run() -> None:
        ui.print_info(f"Checking connection to '{config.model.model_name}' at {config.model.endpoint}...")
        adapter = create_adapter(config.model)
        health = await adapter.check_health()

        if health.healthy:
            if health.details.get("status") == "Operating in Fallback Mode":
                ui.print_warning(f"Primary model '{config.model.model_name}' is UNAVAILABLE.")
                ui.print_info(f"Fallback Active: '{health.details.get('active_fallback')}' at {health.details.get('fallback_endpoint')}")
            else:
                ui.print_info(f"Model: {config.model.model_name} is AVAILABLE and healthy.")
                ui.print_info(f"Details: {health.details.get('status') or health.details.get('message', 'Ready')}")
        else:
            ui.print_error(f"Model unreachable: {health.error or 'Connection refused'}")

    asyncio.run(_run())


@models_app.command(name="use")
def use_cmd(
    model_name: str = typer.Argument(..., help="Model name identifier (e.g. qwen3.6:35b, mixtral:latest)"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Optional provider override (ollama, openai-local, codemind-local)"),
    endpoint: Optional[str] = typer.Option(None, "--endpoint", "-e", help="Optional endpoint URL override"),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Switch the active model and persist the choice in .codemind/config.json."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)

    async def _run() -> None:
        ui.print_info(f"Searching for model '{model_name}'...")
        discovered = await ModelDiscovery.discover_all(config)

        # Match exact or substring
        target_model: DiscoveredModel | None = None
        for m in discovered:
            if m.name.lower() == model_name.lower():
                target_model = m
                break

        if not target_model:
            # Try partial match
            for m in discovered:
                if model_name.lower() in m.name.lower():
                    target_model = m
                    break

        if target_model:
            selected_name = target_model.name
            selected_provider = provider or target_model.provider
            selected_endpoint = endpoint or target_model.endpoint
        else:
            # If not discovered, allow user to set it anyway with fallback to configured provider/endpoint
            selected_name = model_name
            selected_provider = provider or config.model.provider.value
            selected_endpoint = endpoint or config.model.endpoint
            ui.print_info(f"Model '{model_name}' not listed in local catalog; configuring manual endpoint.")

        # Update and save config
        config.model.model_name = selected_name
        # Match provider enum
        for p in ModelProvider:
            if p.value == selected_provider:
                config.model.provider = p
                break
        config.model.endpoint = selected_endpoint

        saved_path = config.save(workspace_dir=ws)

        if config.plain_mode:
            print(f"Active model set to '{selected_name}' (Provider: {selected_provider})")
            print(f"Saved configuration to: {saved_path}")
        else:
            msg = Text()
            msg.append("Successfully switched model:\n\n", style="bold")
            msg.append("  Model:    ", style="bold")
            msg.append(f"{selected_name}\n", style=f"bold {COLOR_ACCENT}")
            msg.append("  Provider: ", style="bold")
            msg.append(f"{selected_provider}\n", style=COLOR_INFO)
            msg.append("  Endpoint: ", style="bold")
            msg.append(f"{selected_endpoint}\n", style="cyan")
            msg.append(f"  Config:   {saved_path}", style="dim")

            ui.console.print(Panel(msg, title=f"[{COLOR_SUCCESS}]Model Activated[/{COLOR_SUCCESS}]", border_style=COLOR_SUCCESS))

    asyncio.run(_run())


@models_app.command(name="test")
def test_cmd(
    model_name: Optional[str] = typer.Argument(None, help="Target model to test (defaults to current model)"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Provider for target model (ollama, openai-local)"),
    endpoint: Optional[str] = typer.Option(None, "--endpoint", "-e", help="Endpoint URL for target model"),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Run non-destructive agent capability benchmark suite against a model."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)

    target_name = model_name or config.model.model_name
    target_provider = provider or config.model.provider.value
    target_endpoint = endpoint or config.model.endpoint

    async def _run() -> None:
        ui.print_info(f"Starting agent capability test suite for '{target_name}' via {target_provider}...")
        # Build test settings
        test_settings = ModelSettings(
            model_name=target_name,
            endpoint=target_endpoint,
            timeout_seconds=90,
        )
        for p in ModelProvider:
            if p.value == target_provider:
                test_settings.provider = p
                break

        adapter = create_adapter(test_settings)
        tester = ModelCapabilityTester(adapter)

        res = await tester.evaluate_all()

        if config.plain_mode:
            print("\n" + "=" * 50)
            print(res.format_report())
            print("=" * 50 + "\n")
            return

        table = Table(
            title=f"[bold #FF9E3B]Capability Evaluation: {target_name}[/bold #FF9E3B]",
            show_header=True,
            header_style="bold cyan",
            border_style=COLOR_MUTED,
        )
        table.add_column("Capability Dimension", width=25)
        table.add_column("Result", width=12, justify="center")
        table.add_column("Latency", width=10, justify="right")
        table.add_column("Output Excerpt / Notes", style="dim")

        for p in res.probes:
            res_str = f"[{COLOR_SUCCESS}]✓ Passed[/{COLOR_SUCCESS}]" if p.passed else f"[{COLOR_DANGER}]✗ Failed[/{COLOR_DANGER}]"
            table.add_row(
                p.dimension,
                res_str,
                f"{p.latency_seconds:.2f}s",
                p.details if not p.passed else p.output_snippet.replace("\n", " "),
            )

        ui.console.print(table)

        summary_text = Text()
        summary_text.append(f"Model: {target_name} ({target_provider})\n", style="bold")
        summary_text.append(f"Connection: {res.connection_status}\n", style=COLOR_INFO)
        summary_text.append(f"Agent Compatibility Rating: {res.compatibility_rating}\n", style=f"bold {COLOR_ACCENT}")
        rec_color = COLOR_SUCCESS if res.recommended_for_agent else COLOR_WARNING
        summary_text.append(
            f"Recommended as Agent Provider: {'Yes' if res.recommended_for_agent else 'Limited / Not Recommended'}",
            style=f"bold {rec_color}",
        )

        ui.console.print(
            Panel(
                summary_text,
                title="[bold]Evaluation Summary[/bold]",
                border_style=COLOR_ACCENT,
                padding=(1, 2),
            )
        )

    asyncio.run(_run())


@models_app.command(name="compare")
def compare_cmd(
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Compare performance, context window, and capability profiles of available models."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)

    table = Table(
        title="[bold #FF9E3B]Model Provider Architectural Comparison[/bold #FF9E3B]",
        show_header=True,
        header_style="bold cyan",
        border_style=COLOR_MUTED,
    )
    table.add_column("Model / Provider", style="bold white")
    table.add_column("Type", style="cyan")
    table.add_column("Context Window", justify="right")
    table.add_column("Tool Protocol", style="green")
    table.add_column("Status / Role", style="yellow")

    table.add_row(
        "codemind\n(codemind-custom)",
        "Foundation (vLLM/OpenAI-compat)",
        "32k - 65k",
        "Native v1 JSON ReAct",
        "Target Foundation Provider",
    )
    table.add_row(
        "qwen3.6:35b\n(ollama)",
        "Community Local (Ollama)",
        "32k - 262k",
        "Prompted v1 JSON",
        "Active Baseline Provider",
    )
    table.add_row(
        "mock-model\n(mock)",
        "In-Memory Deterministic",
        "65k",
        "Hermetic v1 JSON",
        "Offline Test Provider",
    )

    if config.plain_mode:
        print("\nModel Provider Comparison:")
        print(f"{'PROVIDER':<20} {'CONTEXT':<12} {'PROTOCOL':<20} {'ROLE':<25}")
        print("-" * 77)
        print(f"{'codemind-custom':<20} {'32k-65k':<12} {'Native v1 JSON':<20} {'Target Foundation Model':<25}")
        print(f"{'ollama (qwen3.6:35b)':<20} {'32k-262k':<12} {'Prompted v1 JSON':<20} {'Active Baseline Provider':<25}")
        print(f"{'mock-model':<20} {'65k':<12} {'Hermetic v1 JSON':<20} {'Offline Test Suite':<25}\n")
    else:
        ui.console.print(table)
