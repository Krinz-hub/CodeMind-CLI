"""CLI commands for discovering, inspecting, validating, and managing CodeMind engineering skills."""

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
from codemind.skills.registry import SkillRegistry

skills_app = typer.Typer(
    name="skills",
    help="Discover, inspect, validate, and manage specialized engineering skills.",
    invoke_without_command=True,
)


@skills_app.callback(invoke_without_command=True)
def skills_default(
    ctx: typer.Context,
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Default handler for 'codemind skills' - lists available skills."""
    if ctx.invoked_subcommand is None:
        list_cmd(plain=plain, workspace=workspace)


@skills_app.command(name="list")
def list_cmd(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category (backend, frontend, database, etc.)."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Display discovered skills across built-in, user, and project tiers."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    registry = SkillRegistry(ws)

    skills = registry.discover_all()
    if category:
        skills = [s for s in skills if s.category.lower() == category.lower()]

    if not skills:
        ui.print_info("No skills discovered matching criteria.")
        return

    if config.plain_mode:
        print("\nAvailable Engineering Skills:")
        print(f"{'STATUS':<10} {'SOURCE':<10} {'NAME':<24} {'VER':<8} {'CATEGORY':<14} {'DESCRIPTION':<35}")
        print("-" * 105)
        for s in skills:
            status_str = "ENABLED" if s.enabled else "DISABLED"
            desc = s.description[:33] + ".." if len(s.description) > 35 else s.description
            print(f"{status_str:<10} {s.source:<10} {s.name:<24} {s.version:<8} {s.category:<14} {desc:<35}")
        print()
        return

    table = Table(
        title="[bold #FF9E3B]Discovered Engineering Skills[/bold #FF9E3B]",
        show_header=True,
        header_style="bold cyan",
        border_style=COLOR_MUTED,
    )
    table.add_column("Status", width=10, justify="center")
    table.add_column("Source", width=10, style="dim")
    table.add_column("Skill Name", style="bold white", width=24)
    table.add_column("Version", style="green", width=8)
    table.add_column("Category", style="yellow", width=14)
    table.add_column("Description", style="white")

    for s in skills:
        status_tag = "[bold green]ENABLED[/bold green]" if s.enabled else "[bold red]DISABLED[/bold red]"
        table.add_row(
            status_tag,
            s.source,
            s.name,
            f"v{s.version}",
            s.category,
            s.description,
        )

    ui.console.print(table)


@skills_app.command(name="show")
def show_cmd(
    name: str = typer.Argument(..., help="Name of the skill to display."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Render complete workflow instructions, constraints, and verification protocol for a skill."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    registry = SkillRegistry(ws)

    skill = registry.get_skill(name)
    if not skill:
        ui.print_error(f"Skill '{name}' not found.")
        raise typer.Exit(code=1)

    if config.plain_mode:
        print(f"\n=== Skill: {skill.name} (v{skill.version}) ===")
        print(f"Source:      {skill.source} ({skill.path})")
        print(f"Category:    {skill.category}")
        print(f"Status:      {'ENABLED' if skill.enabled else 'DISABLED'}")
        print(f"Description: {skill.description}\n")

        if skill.workflow_steps:
            print("Procedural Workflow Steps:")
            for step in skill.workflow_steps:
                print(f"  {step}")
            print()

        if skill.constraints:
            print("Authoritative Constraints:")
            for c in skill.constraints:
                print(f"  - {c}")
            print()

        if skill.verification:
            print("Verification Protocol:")
            for v in skill.verification:
                print(f"  - {v}")
            print()

        print("Instructions:")
        print(skill.instructions)
        print()
        return

    # Rich formatted rendering
    ui.console.print(
        Panel(
            f"[bold white]{skill.name}[/bold white] [dim](v{skill.version} - {skill.category})[/dim]\n[italic]{skill.description}[/italic]",
            title="[bold #FF9E3B]Engineering Skill Overview[/bold #FF9E3B]",
            border_style=COLOR_ACCENT,
        )
    )

    if skill.workflow_steps:
        ui.console.print("\n[bold cyan]▶ Procedural Workflow Steps:[/bold cyan]")
        for step in skill.workflow_steps:
            ui.console.print(f"  [bold green]•[/bold green] {step}")

    if skill.constraints:
        ui.console.print("\n[bold yellow]▶ Authoritative Constraints:[/bold yellow]")
        for c in skill.constraints:
            ui.console.print(f"  [bold red]✗[/bold red] {c}")

    if skill.verification:
        ui.console.print("\n[bold magenta]▶ Verification Protocol:[/bold magenta]")
        for v in skill.verification:
            ui.console.print(f"  [bold green]✓[/bold green] {v}")

    ui.console.print("\n[bold white]▶ Detailed Execution Instructions:[/bold white]")
    ui.console.print(skill.instructions)
    ui.console.print()


@skills_app.command(name="search")
def search_cmd(
    query: str = typer.Argument(..., help="Search query string."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Search skills by keywords, intent, description, or category."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    registry = SkillRegistry(ws)

    matches = registry.search_skills(query)
    if not matches:
        ui.print_info(f"No skills matched query '{query}'.")
        return

    if config.plain_mode:
        print(f"\nSkills matching '{query}' ({len(matches)} found):")
        for s in matches:
            print(f"- {s.name:<24} [{s.category}] v{s.version}: {s.description}")
        print()
        return

    table = Table(
        title=f"[bold #FF9E3B]Search Results for '{query}'[/bold #FF9E3B]",
        show_header=True,
        header_style="bold cyan",
        border_style=COLOR_MUTED,
    )
    table.add_column("Skill Name", style="bold white", width=24)
    table.add_column("Category", style="yellow", width=14)
    table.add_column("Version", style="green", width=8)
    table.add_column("Description", style="white")

    for s in matches:
        table.add_row(s.name, s.category, f"v{s.version}", s.description)

    ui.console.print(table)


@skills_app.command(name="validate")
def validate_cmd(
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Scan all skill directories and validate manifests against schema."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    registry = SkillRegistry(ws)

    issues = registry.validate_all()
    skills = registry.discover_all()

    if not issues:
        ui.print_success(f"Validation successful: All {len(skills)} discovered skills passed schema validation.")
        return

    ui.print_error(f"Validation found {len(issues)} issue(s):")
    for issue in issues:
        sev = issue.severity.upper()
        if config.plain_mode:
            print(f"[{sev}] {issue.skill_path}: {issue.message}")
        else:
            color = "red" if issue.severity == "error" else "yellow"
            ui.console.print(f"  [bold {color}][{sev}][/bold {color}] [dim]{issue.skill_path}[/dim]: {issue.message}")


@skills_app.command(name="enable")
def enable_cmd(
    name: str = typer.Argument(..., help="Name of the skill to enable."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Enable a skill for the active project."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    registry = SkillRegistry(ws)

    ok = registry.set_skill_enabled(name, enabled=True)
    if not ok:
        ui.print_error(f"Skill '{name}' not found.")
        raise typer.Exit(code=1)

    ui.print_success(f"Skill '{name}' is now ENABLED for this workspace.")


@skills_app.command(name="disable")
def disable_cmd(
    name: str = typer.Argument(..., help="Name of the skill to disable."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Disable a skill for the active project."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    registry = SkillRegistry(ws)

    ok = registry.set_skill_enabled(name, enabled=False)
    if not ok:
        ui.print_error(f"Skill '{name}' not found.")
        raise typer.Exit(code=1)

    ui.print_success(f"Skill '{name}' is now DISABLED for this workspace.")


@skills_app.command(name="inspect")
def inspect_cmd(
    name: str = typer.Argument(..., help="Name of the skill to inspect."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Deep inspection of a skill's metadata, dependencies, conflicts, and activation triggers."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    registry = SkillRegistry(ws)

    skill = registry.get_skill(name)
    if not skill:
        ui.print_error(f"Skill '{name}' not found.")
        raise typer.Exit(code=1)

    manifest = skill.manifest
    m = manifest.triggers

    if config.plain_mode:
        print(f"\nDeep Inspection: {skill.name} (v{skill.version})")
        print(f"Path:          {skill.path}")
        print(f"Source Tier:   {skill.source}")
        print(f"Category:      {skill.category}")
        print(f"Status:        {'ENABLED' if skill.enabled else 'DISABLED'}")
        print(f"Required Tools: {', '.join(manifest.required_tools) or 'None'}")
        print(f"Dependencies:   {', '.join(manifest.dependencies) or 'None'}")
        print(f"Conflicts:      {', '.join(manifest.conflicts) or 'None'}")
        print("Triggers:")
        print(f"  Manifests: {', '.join(m.manifests) or 'None'}")
        print(f"  Globs:     {', '.join(m.globs) or 'None'}")
        print(f"  Keywords:  {', '.join(m.keywords) or 'None'}")
        print(f"Workflow Steps ({len(manifest.workflow_steps)}):")
        for s in manifest.workflow_steps:
            print(f"  {s}")
        print(f"Constraints ({len(manifest.constraints)}):")
        for c in manifest.constraints:
            print(f"  - {c}")
        print()
        return

    table = Table(
        title=f"[bold #FF9E3B]Deep Inspection: {skill.name}[/bold #FF9E3B]",
        show_header=True,
        header_style="bold cyan",
        border_style=COLOR_MUTED,
    )
    table.add_column("Property", style="bold white", width=18)
    table.add_column("Value", style="green")

    table.add_row("Name", skill.name)
    table.add_row("Version", f"v{skill.version}")
    table.add_row("Source Tier", skill.source)
    table.add_row("Category", skill.category)
    table.add_row("Status", "[bold green]ENABLED[/bold green]" if skill.enabled else "[bold red]DISABLED[/bold red]")
    table.add_row("File Path", skill.path)
    table.add_row("Required Tools", ", ".join(manifest.required_tools) or "None")
    table.add_row("Dependencies", ", ".join(manifest.dependencies) or "None")
    table.add_row("Conflicts", ", ".join(manifest.conflicts) or "None")
    table.add_row("Manifest Triggers", ", ".join(m.manifests) or "None")
    table.add_row("Glob Triggers", ", ".join(m.globs) or "None")
    table.add_row("Keyword Triggers", ", ".join(m.keywords) or "None")

    ui.console.print(table)
