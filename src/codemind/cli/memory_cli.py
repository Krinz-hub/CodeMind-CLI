"""CLI commands for inspecting, searching, updating, and managing persistent project memory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from codemind.cli.branding import COLOR_ACCENT, COLOR_DANGER, COLOR_INFO, COLOR_MUTED, COLOR_SUCCESS, COLOR_WARNING
from codemind.cli.ui import TerminalUI
from codemind.config import CodeMindConfig
from codemind.context.discovery import ProjectDiscovery
from codemind.memory.models import MemoryLayer, MemoryStatus
from codemind.memory.store import SQLiteProjectMemory

memory_app = typer.Typer(
    name="memory",
    help="Inspect, query, update, and manage persistent project memory across sessions.",
    invoke_without_command=True,
)


@memory_app.callback(invoke_without_command=True)
def memory_default(
    ctx: typer.Context,
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Default handler for 'codemind memory' - displays status overview."""
    if ctx.invoked_subcommand is None:
        status_cmd(plain=plain, workspace=workspace)


@memory_app.command(name="status")
def status_cmd(
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Display overall health, record counts, and database metrics."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    store = SQLiteProjectMemory(ws)
    stats = store.get_stats()

    size_kb = round(stats.db_size_bytes / 1024, 2)
    last_up = stats.last_updated or "Never"

    if config.plain_mode:
        print("\n=== Persistent Project Memory Status ===")
        print(f"Database File:   {stats.db_path}")
        print(f"Schema Version:  v{stats.schema_version}")
        print(f"File Size:       {size_kb} KB")
        print(f"Total Entries:   {stats.total_entries}")
        print(f"Last Updated:    {last_up}")
        print("\nEntries by Layer:")
        for layer in ["project", "decision", "task", "instruction"]:
            cnt = stats.by_layer.get(layer, 0)
            print(f"  - Layer {layer.capitalize():<12}: {cnt}")
        print("\nEntries by Status:")
        for status, cnt in stats.by_status.items():
            print(f"  - {status:<15}: {cnt}")
        print()
        return

    table = Table(
        title="[bold #FF9E3B]Persistent Project Memory Status[/bold #FF9E3B]",
        show_header=True,
        header_style="bold cyan",
        border_style=COLOR_MUTED,
    )
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="green")

    table.add_row("Database Path", stats.db_path)
    table.add_row("Schema Version", f"v{stats.schema_version}")
    table.add_row("Database Size", f"{size_kb} KB")
    table.add_row("Total Entries", str(stats.total_entries))
    table.add_row("Last Updated", last_up)

    layer_breakdown = ", ".join(f"{l}: {c}" for l, c in stats.by_layer.items()) or "None"
    table.add_row("By Layer", layer_breakdown)

    status_breakdown = ", ".join(f"{s}: {c}" for s, c in stats.by_status.items()) or "None"
    table.add_row("By Status", status_breakdown)

    ui.console.print(table)


@memory_app.command(name="show")
def show_cmd(
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Render a human-readable summary of project identity, decisions, tasks, and guidelines."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    store = SQLiteProjectMemory(ws)

    entries = store.list_entries(status=MemoryStatus.ACTIVE, limit=100)

    by_layer: dict[str, list] = {"project": [], "decision": [], "task": [], "instruction": []}
    for e in entries:
        by_layer[e.layer.value].append(e)

    if config.plain_mode:
        print("\n=== Active Project Memory Snapshot ===\n")
        print("--- [Layer A: Project Identity & Architecture] ---")
        if not by_layer["project"]:
            print("  (No project identity records stored)")
        for p in by_layer["project"]:
            print(f"* {p.title} ({p.category}):\n  {p.content}\n")

        print("--- [Layer D: Workspace Directives] ---")
        if not by_layer["instruction"]:
            print("  (No workspace directives stored)")
        for i in by_layer["instruction"]:
            print(f"* {i.title}: {i.content}")
        print()

        print("--- [Layer B: Architectural Decisions (ADRs)] ---")
        if not by_layer["decision"]:
            print("  (No decision records stored)")
        for d in by_layer["decision"]:
            print(f"* {d.title}: {d.content}")
        print()

        print("--- [Layer C: Recent Tasks & History] ---")
        if not by_layer["task"]:
            print("  (No task history stored)")
        for t in by_layer["task"][:10]:
            print(f"* [{t.category.upper()}] {t.title}: {t.content}")
        print()
        return

    # Rich formatted output
    ui.console.print(Panel("[bold white]Active Project Knowledge Snapshot[/bold white]", border_style=COLOR_ACCENT))

    # Layer A
    ui.console.print("\n[bold cyan]▶ Layer A: Project Identity & Architecture[/bold cyan]")
    if not by_layer["project"]:
        ui.console.print("  [dim]No project identity records stored.[/dim]")
    for p in by_layer["project"]:
        ui.console.print(f"  [bold green]• {p.title}[/bold green] [dim]({p.category})[/dim]")
        ui.console.print(f"    {p.content.strip()}\n")

    # Layer D
    ui.console.print("[bold cyan]▶ Layer D: Workspace Guidelines & Constraints[/bold cyan]")
    if not by_layer["instruction"]:
        ui.console.print("  [dim]No workspace directives stored.[/dim]")
    for i in by_layer["instruction"]:
        ui.console.print(f"  [bold yellow]• {i.title}:[/bold yellow] {i.content.strip()}")
    ui.console.print()

    # Layer B
    ui.console.print("[bold cyan]▶ Layer B: Architectural Decisions (ADRs)[/bold cyan]")
    if not by_layer["decision"]:
        ui.console.print("  [dim]No decision records stored.[/dim]")
    for d in by_layer["decision"]:
        ui.console.print(f"  [bold white]• {d.title}:[/bold white] {d.content.strip()}")
    ui.console.print()

    # Layer C
    ui.console.print("[bold cyan]▶ Layer C: Operational Task History[/bold cyan]")
    if not by_layer["task"]:
        ui.console.print("  [dim]No task history stored.[/dim]")
    for t in by_layer["task"][:10]:
        cat_color = "green" if t.category == "feature" else ("red" if t.category == "unresolved_issue" else "yellow")
        ui.console.print(f"  [{cat_color}]• [{t.category.upper()}][/{cat_color}] [bold]{t.title}:[/bold] {t.content.strip()}")
    ui.console.print()


@memory_app.command(name="search")
def search_cmd(
    query: str = typer.Argument(..., help="Search terms or query string."),
    layer: Optional[str] = typer.Option(None, "--layer", "-l", help="Filter by layer (project, decision, task, instruction)."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Execute FTS5 full-text search across all persistent project memories."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    store = SQLiteProjectMemory(ws)

    results = store.search(query=query, layer=layer, limit=20)

    if not results:
        ui.print_info(f"No memories matched search query '{query}'.")
        return

    if config.plain_mode:
        print(f"\nSearch Results for '{query}' ({len(results)} found):")
        print(f"{'SCORE':<8} {'LAYER':<12} {'STALE':<8} {'ID':<18} {'TITLE':<35}")
        print("-" * 85)
        for r in results:
            stale_str = "YES" if r.is_stale else "no"
            print(f"{r.score:<8.2f} {r.entry.layer.value:<12} {stale_str:<8} {r.entry.id:<18} {r.entry.title[:33]:<35}")
        print()
        return

    table = Table(
        title=f"[bold #FF9E3B]Memory Search Results for '{query}'[/bold #FF9E3B]",
        show_header=True,
        header_style="bold cyan",
        border_style=COLOR_MUTED,
    )
    table.add_column("Score", width=8, justify="right")
    table.add_column("Layer", style="cyan", width=12)
    table.add_column("Stale", width=8, justify="center")
    table.add_column("ID", style="dim", width=18)
    table.add_column("Title", style="bold white")
    table.add_column("Content Snippet", style="white")

    for r in results:
        stale_badge = "[bold red]STALE[/bold red]" if r.is_stale else "[green]ok[/green]"
        snippet = (r.entry.content[:60] + "...") if len(r.entry.content) > 60 else r.entry.content
        table.add_row(
            f"{r.score:.2f}",
            r.entry.layer.value,
            stale_badge,
            r.entry.id,
            r.entry.title,
            snippet.replace("\n", " "),
        )

    ui.console.print(table)


@memory_app.command(name="list")
def list_cmd(
    layer: Optional[str] = typer.Option(None, "--layer", "-l", help="Filter by layer (project, decision, task, instruction)."),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status (active, superseded, deprecated)."),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum entries to list."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """List memory entries with optional filtering by layer and status."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    store = SQLiteProjectMemory(ws)

    entries = store.list_entries(layer=layer, status=status, limit=limit)

    if not entries:
        ui.print_info("No memory entries found matching criteria.")
        return

    if config.plain_mode:
        print(f"\nMemory Entries ({len(entries)}):")
        print(f"{'ID':<18} {'LAYER':<12} {'CATEGORY':<14} {'STATUS':<12} {'PIN':<5} {'TITLE':<30}")
        print("-" * 95)
        for e in entries:
            pin_str = "*" if e.pinned else " "
            print(f"{e.id:<18} {e.layer.value:<12} {e.category:<14} {e.status.value:<12} {pin_str:<5} {e.title[:28]:<30}")
        print()
        return

    table = Table(
        title="[bold #FF9E3B]Persistent Memory Entries[/bold #FF9E3B]",
        show_header=True,
        header_style="bold cyan",
        border_style=COLOR_MUTED,
    )
    table.add_column("ID", style="dim", width=18)
    table.add_column("Layer", style="cyan", width=12)
    table.add_column("Category", style="yellow", width=14)
    table.add_column("Status", width=12)
    table.add_column("Pinned", width=8, justify="center")
    table.add_column("Title", style="bold white")
    table.add_column("Updated", style="dim", width=20)

    for e in entries:
        status_style = "green" if e.status == MemoryStatus.ACTIVE else ("yellow" if e.status == MemoryStatus.SUPERSEDED else "red")
        pin_badge = "[bold yellow]YES[/bold yellow]" if e.pinned else "[dim]no[/dim]"
        table.add_row(
            e.id,
            e.layer.value,
            e.category,
            f"[{status_style}]{e.status.value}[/{status_style}]",
            pin_badge,
            e.title,
            e.updated_at[:19],
        )

    ui.console.print(table)


@memory_app.command(name="update")
def update_cmd(
    entry_id: str = typer.Argument(..., help="ID of the memory record to update."),
    title: Optional[str] = typer.Option(None, "--title", help="New title for the memory item."),
    content: Optional[str] = typer.Option(None, "--content", help="New content text."),
    status: Optional[str] = typer.Option(None, "--status", help="New status (active, superseded, deprecated)."),
    pin: Optional[bool] = typer.Option(None, "--pin/--unpin", help="Pin or unpin from prompt injection."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Manually update or change status/pinning of a memory record."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    store = SQLiteProjectMemory(ws)

    updated = store.update_entry(
        entry_id=entry_id,
        title=title,
        content=content,
        status=status,
        pinned=pin,
    )

    if not updated:
        ui.print_error(f"Memory entry '{entry_id}' not found.")
        raise typer.Exit(code=1)

    ui.print_success(f"Successfully updated memory entry '{entry_id}' (Status: {updated.status.value}, Pinned: {updated.pinned}).")


@memory_app.command(name="rebuild")
def rebuild_cmd(
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Re-scan workspace structure and refresh baseline Layer A (Project Memory) from ground truth."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    store = SQLiteProjectMemory(ws)

    ui.print_info(f"Rebuilding project memory for workspace '{ws}'...")
    discovery = ProjectDiscovery(ws)
    summary = discovery.analyze()

    count = store.rebuild_from_project(summary)
    ui.print_success(f"Rebuild complete. Refreshed {count} baseline project memory record(s).")


@memory_app.command(name="clear")
def clear_cmd(
    layer: Optional[str] = typer.Option(None, "--layer", "-l", help="Purge only a specific layer."),
    force: bool = typer.Option(False, "--force", "-f", help="Bypass confirmation prompt."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Safely purge memory entries (optionally filtered by layer)."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    store = SQLiteProjectMemory(ws)

    target_desc = f"all entries in layer '{layer}'" if layer else "ALL persistent project memories"

    if not force:
        confirm = typer.confirm(f"Are you sure you want to permanently delete {target_desc}?", default=False)
        if not confirm:
            ui.print_info("Clear aborted.")
            return

    count = store.clear(layer=layer)
    ui.print_success(f"Purged {count} memory record(s) from persistent store.")
