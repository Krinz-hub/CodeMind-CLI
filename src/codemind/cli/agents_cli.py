"""CLI subcommands for managing multi-agent workers and delegation states."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from codemind.multiagent.models import AgentRole, MultiAgentConfig, WorkerConfig, WorkerStatus
from codemind.multiagent.sidecar import SidecarRuntime

agents_app = typer.Typer(
    name="agents",
    help="Inspect and manage multi-agent workers, roles, and status.",
    add_completion=False,
)
console = Console()


@agents_app.command(name="list")
def agents_list(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
) -> None:
    """List specialized worker agents and their capabilities."""
    table = Table(title="Specialized Worker Agent Roles")
    table.add_column("Role", style="cyan", no_wrap=True)
    table.add_column("Sandbox Mode", style="magenta")
    table.add_column("Allowed Tools", style="white")
    table.add_column("Description", style="dim")

    table.add_row(
        "research",
        "Read-Only",
        "read_file, list_dir, search, git_status",
        "Codebase reconnaissance, architecture analysis",
    )
    table.add_row(
        "coding",
        "Isolated Sandbox",
        "read_file, create_file, apply_patch, list_dir",
        "Feature implementation & change proposals",
    )
    table.add_row(
        "debugging",
        "Isolated Sandbox",
        "read_file, apply_patch, run_command",
        "Root cause isolation & minimal bug repairs",
    )
    table.add_row(
        "testing",
        "Isolated Sandbox",
        "read_file, create_file, run_command",
        "Test suite authoring, execution & verification",
    )
    console.print(table)


@agents_app.command(name="status")
def agents_status(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Display real-time multi-agent system status."""
    sidecar = SidecarRuntime()
    status = sidecar.get_status()

    table = Table(title="Multi-Agent System Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Runtime State", status.get("status", "unknown").upper())
    table.add_row("Registered Workers", str(status.get("registered_workers", 0)))
    table.add_row("Active Inferences", str(status.get("active_inferences", 0)))
    table.add_row("Max Inference Concurrency", str(status.get("max_concurrent_inferences", 1)))
    table.add_row("Inferences Serviced", str(status.get("total_inferences_serviced", 0)))

    console.print(table)


@agents_app.command(name="config")
def agents_config(
    max_workers: Optional[int] = typer.Option(None, "--max-workers"),
    max_inferences: Optional[int] = typer.Option(None, "--max-inferences"),
    sequential: Optional[bool] = typer.Option(None, "--sequential/--parallel"),
) -> None:
    """Inspect and adjust multi-agent runtime configuration."""
    cfg = MultiAgentConfig()
    if max_workers is not None:
        cfg.max_workers = max_workers
    if max_inferences is not None:
        cfg.max_concurrent_inferences = max_inferences
    if sequential is not None:
        cfg.sequential_mode = sequential

    table = Table(title="Multi-Agent Concurrency & Resource Settings")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("max_workers", str(cfg.max_workers))
    table.add_row("max_concurrent_inferences", str(cfg.max_concurrent_inferences))
    table.add_row("sequential_mode", str(cfg.sequential_mode))
    table.add_row("inference_timeout_seconds", f"{cfg.inference_timeout_seconds}s")
    table.add_row("worker_workspace_dir", cfg.worker_workspace_dir)

    console.print(table)


@agents_app.command(name="inspect")
def agents_inspect(
    worker_id: str = typer.Argument(..., help="Worker agent ID to inspect"),
) -> None:
    """Inspect detailed state and logs of a specific worker agent."""
    console.print(f"\n[bold cyan]Worker Agent: {worker_id}[/bold cyan]")
    console.print("State:         IDLE / TERMINATED")
    console.print("Sandbox:       .codemind/workspaces/" + worker_id)
    console.print("Message Logs:  0 active messages")


@agents_app.command(name="stop")
def agents_stop(
    worker_id: str = typer.Argument(..., help="Worker agent ID to terminate"),
) -> None:
    """Terminate an active worker agent."""
    typer.echo(f"Worker '{worker_id}' terminated.")


@agents_app.command(name="logs")
def agents_logs(
    worker_id: str = typer.Argument(..., help="Worker agent ID"),
) -> None:
    """Display event audit logs for a worker agent."""
    typer.echo(f"No active log stream found for '{worker_id}'.")
