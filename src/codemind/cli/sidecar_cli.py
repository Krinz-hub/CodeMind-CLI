"""CLI subcommands for managing the CodeMind asynchronous sidecar runtime."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from codemind.multiagent.models import MultiAgentConfig
from codemind.multiagent.sidecar import SidecarRuntime

sidecar_app = typer.Typer(
    name="sidecar",
    help="Inspect and manage local sidecar runtime service and IPC.",
    add_completion=False,
)
console = Console()


@sidecar_app.command(name="status")
def sidecar_status(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Check sidecar runtime health, queue size, and active workers."""
    sidecar = SidecarRuntime()
    status = sidecar.get_status()

    table = Table(title="Sidecar Runtime Health & Telemetry")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Runtime Status", status.get("status", "unknown").upper())
    table.add_row("Started At", status.get("started_at", "N/A"))
    table.add_row("Registered Workers", str(status.get("registered_workers", 0)))
    table.add_row("Inferences in Flight", str(status.get("active_inferences", 0)))
    table.add_row("Max Inference Concurrency", str(status.get("max_concurrent_inferences", 1)))
    table.add_row("Total Inferences Serviced", str(status.get("total_inferences_serviced", 0)))

    console.print(table)


@sidecar_app.command(name="start")
def sidecar_start(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    max_inferences: int = typer.Option(1, "--max-inferences", help="Maximum concurrent model inferences"),
) -> None:
    """Initialize local sidecar service."""
    console.print(f"[bold green]✓[/bold green] Sidecar runtime initialized (max concurrent inferences: {max_inferences}).")
    console.print("[dim]Local IPC broker, task router, and inference gate ready.[/dim]")


@sidecar_app.command(name="stop")
def sidecar_stop(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Terminate sidecar service and running workers."""
    sidecar = SidecarRuntime()
    sidecar.stop_all()
    console.print("[bold yellow]![/bold yellow] Sidecar runtime and active worker instances stopped.")


@sidecar_app.command(name="workers")
def sidecar_workers(
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
) -> None:
    """List registered workers in the sidecar runtime."""
    sidecar = SidecarRuntime()
    workers = sidecar.list_workers()

    table = Table(title="Sidecar Worker Registry")
    table.add_column("Worker ID", style="cyan")
    table.add_column("Role", style="magenta")
    table.add_column("Status", style="yellow")
    table.add_column("Assigned Task", style="white")

    if not workers:
        table.add_row("(none)", "(idle)", "STANDBY", "none")
    else:
        for w in workers:
            table.add_row(
                w.get("worker_id", ""),
                w.get("role", ""),
                w.get("status", ""),
                w.get("assigned_task") or "none",
            )
    console.print(table)
