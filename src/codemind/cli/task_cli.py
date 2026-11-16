"""CLI subcommands for managing workflow tasks, checkpoints, and execution states."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from codemind.config import CodeMindConfig
from codemind.orchestration.checkpoint import CheckpointManager
from codemind.planning.task import TaskPlan, TaskStatus

task_app = typer.Typer(
    name="task",
    help="Manage workflow tasks, inspect execution plans, and control long-running jobs.",
    add_completion=False,
)
console = Console()


@task_app.command(name="status")
def task_status(
    session_id: Optional[str] = typer.Option(
        None,
        "--session",
        "-s",
        help="Session identifier to inspect.",
    ),
    workspace: Optional[str] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Target workspace root.",
    ),
) -> None:
    """Display real-time status of the active or latest task execution plan."""
    ws_root = Path(workspace or os.getcwd()).resolve()
    mgr = CheckpointManager(ws_root)

    # If session not specified, find latest
    ckpts = mgr.list_checkpoints()
    if not ckpts:
        typer.echo(f"No task execution checkpoints found in {ws_root}/.codemind/checkpoints/.")
        return

    target_session = session_id or ckpts[0]["session_id"]
    latest_ckpt = mgr.load_latest_checkpoint(target_session)

    if not latest_ckpt:
        typer.echo(f"Could not load checkpoint for session '{target_session}'.")
        return

    table = Table(title=f"Task Workflow Status: {target_session} ({latest_ckpt.checkpoint_id})")
    table.add_column("Task ID", style="cyan", no_wrap=True)
    table.add_column("Title", style="white")
    table.add_column("Status", style="magenta")
    table.add_column("Dependencies", style="dim")
    table.add_column("Evidence / Outputs", style="green")

    for t in latest_ckpt.tasks:
        tid = t.get("id", "")
        title = t.get("title", "")
        st = t.get("status", "").upper()
        deps = ", ".join(t.get("dependencies", [])) or "None"
        ev = t.get("evidence", "") or ", ".join(t.get("expected_outputs", [])) or "-"
        table.add_row(tid, title, st, deps, ev[:40])

    console.print(table)
    console.print(f"Files Created: {len(latest_ckpt.files_created)} | Files Modified: {len(latest_ckpt.files_modified)} | Total Turns: {latest_ckpt.total_turns}")


@task_app.command(name="inspect")
def task_inspect(
    task_id: str = typer.Argument(..., help="Task identifier (e.g. task-1)"),
    session_id: Optional[str] = typer.Option(
        None,
        "--session",
        "-s",
        help="Session identifier.",
    ),
    workspace: Optional[str] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Target workspace root.",
    ),
) -> None:
    """Inspect detailed task node, dependencies, verification criteria, and evidence."""
    ws_root = Path(workspace or os.getcwd()).resolve()
    mgr = CheckpointManager(ws_root)
    ckpts = mgr.list_checkpoints()
    if not ckpts:
        typer.echo("No checkpoints found.")
        return

    target_session = session_id or ckpts[0]["session_id"]
    latest_ckpt = mgr.load_latest_checkpoint(target_session)
    if not latest_ckpt:
        typer.echo(f"No checkpoint found for session '{target_session}'.")
        return

    matching_task = next((t for t in latest_ckpt.tasks if t.get("id") == task_id), None)
    if not matching_task:
        typer.echo(f"Task '{task_id}' not found in session '{target_session}'.")
        return

    console.print(f"\n[bold cyan]Task Node: {task_id}[/bold cyan]")
    console.print(f"Title:         {matching_task.get('title')}")
    console.print(f"Status:        {matching_task.get('status', '').upper()}")
    console.print(f"Priority:      {matching_task.get('priority', 'normal')}")
    console.print(f"Complexity:    {matching_task.get('complexity', 'moderate')}")
    console.print(f"Dependencies:  {', '.join(matching_task.get('dependencies', [])) or 'None'}")
    console.print(f"Outputs:       {', '.join(matching_task.get('expected_outputs', [])) or 'None'}")
    console.print(f"Relevant:      {', '.join(matching_task.get('relevant_files', [])) or 'None'}")
    console.print(f"Retries:       {matching_task.get('retry_count', 0)}")
    console.print(f"Evidence:      {matching_task.get('evidence', 'None')}")


@task_app.command(name="pause")
def task_pause(
    session_id: str = typer.Argument(..., help="Session ID to pause"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Safely pause a running workflow and checkpoint its current state."""
    ws_root = Path(workspace or os.getcwd()).resolve()
    mgr = CheckpointManager(ws_root)
    ckpt = mgr.load_latest_checkpoint(session_id)
    if not ckpt:
        typer.echo(f"Session '{session_id}' not found.")
        return
    # Write pause flag
    ckpt.is_completed = False
    mgr.save_checkpoint_atomic(ckpt)
    typer.echo(f"Workflow '{session_id}' safely paused at checkpoint '{ckpt.checkpoint_id}'.")


@task_app.command(name="resume")
def task_resume(
    session_id: str = typer.Argument(..., help="Session ID to resume"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Resume execution of a paused or interrupted workflow."""
    ws_root = Path(workspace or os.getcwd()).resolve()
    mgr = CheckpointManager(ws_root)
    ckpt = mgr.load_latest_checkpoint(session_id)
    if not ckpt:
        typer.echo(f"No checkpoint found for session '{session_id}'.")
        return
    typer.echo(f"Ready to resume workflow '{session_id}' from checkpoint '{ckpt.checkpoint_id}'.")
    typer.echo(f"Pending tasks: {len(ckpt.pending_task_ids)} | Completed: {len(ckpt.completed_task_ids)}")


@task_app.command(name="cancel")
def task_cancel(
    session_id: str = typer.Argument(..., help="Session ID to cancel"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Cancel pending tasks in a workflow and mark it CANCELLED."""
    ws_root = Path(workspace or os.getcwd()).resolve()
    mgr = CheckpointManager(ws_root)
    ckpt = mgr.load_latest_checkpoint(session_id)
    if not ckpt:
        typer.echo(f"Session '{session_id}' not found.")
        return
    for t in ckpt.tasks:
        if t.get("status") in ("pending", "ready", "running", "waiting_for_approval"):
            t["status"] = "cancelled"
    ckpt.is_completed = True
    mgr.save_checkpoint_atomic(ckpt)
    typer.echo(f"Workflow '{session_id}' cancelled. Remaining tasks marked CANCELLED.")


@task_app.command(name="history")
def task_history(
    session_id: Optional[str] = typer.Option(None, "--session", "-s"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
) -> None:
    """Display history of past workflow runs and checkpoints."""
    ws_root = Path(workspace or os.getcwd()).resolve()
    mgr = CheckpointManager(ws_root)
    ckpts = mgr.list_checkpoints(session_id)
    if not ckpts:
        typer.echo("No workflow checkpoint history found.")
        return

    table = Table(title="Workflow Checkpoint History")
    table.add_column("Session ID", style="cyan", no_wrap=False)
    table.add_column("Checkpoint ID", style="white", no_wrap=False)
    table.add_column("Timestamp", style="dim")
    table.add_column("Completed", style="green")
    table.add_column("Pending", style="yellow")
    table.add_column("Status", style="magenta")

    for c in ckpts:
        status_label = "FINISHED" if c.get("is_completed") else "ACTIVE / PAUSED"
        table.add_row(
            c.get("session_id", ""),
            c.get("checkpoint_id", ""),
            c.get("timestamp", "")[:19],
            str(c.get("completed_tasks", 0)),
            str(c.get("pending_tasks", 0)),
            status_label,
        )

    console.print(table)
