"""CLI commands for managing Model Context Protocol (MCP) servers and external tools."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from codemind.cli.branding import COLOR_ACCENT, COLOR_DANGER, COLOR_INFO, COLOR_MUTED, COLOR_SUCCESS, COLOR_WARNING
from codemind.cli.ui import TerminalUI
from codemind.config import CodeMindConfig
from codemind.mcp.client import MCPClient
from codemind.mcp.manager import MCPManager
from codemind.mcp.models import MCPTransportType


mcp_app = typer.Typer(
    name="mcp",
    help="Configure, inspect, test, and manage external Model Context Protocol (MCP) servers.",
    invoke_without_command=True,
)


@mcp_app.callback(invoke_without_command=True)
def mcp_default(
    ctx: typer.Context,
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Default handler for 'codemind mcp' - lists configured servers."""
    if ctx.invoked_subcommand is None:
        list_cmd(plain=plain, workspace=workspace)


@mcp_app.command(name="list")
def list_cmd(
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """List all configured MCP servers and their discovered tools."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    mcp_mgr = MCPManager(ws)

    servers = mcp_mgr.list_servers()
    if not servers:
        ui.print_info("No MCP servers configured in .codemind/mcp.json.")
        ui.print_info("Add one with: 'codemind mcp add <name> <command-or-url>'")
        return

    if config.plain_mode:
        print("\nConfigured Model Context Protocol (MCP) Servers:")
        print(f"{'STATUS':<12} {'NAME':<18} {'TRANSPORT':<12} {'ENDPOINT / COMMAND':<35} {'TOOLS':<8}")
        print("-" * 85)
        for s in servers:
            status_str = "DISABLED" if s["disabled"] else "ENABLED"
            endpoint = s["url"] if s.get("url") else f"{s['command']} {' '.join(s.get('args', []))}".strip()
            print(f"{status_str:<12} {s['name']:<18} {s['transport'].upper():<12} {endpoint[:35]:<35} {s['tool_count']:<8}")
        print()
    else:
        table = Table(
            title="Model Context Protocol (MCP) Servers",
            header_style=f"bold {COLOR_ACCENT}",
            box=None,
        )
        table.add_column("Status", width=12)
        table.add_column("Name", style="bold", width=18)
        table.add_column("Transport", width=12)
        table.add_column("Command / URL", style=COLOR_MUTED)
        table.add_column("Tools", justify="right", width=8)

        for s in servers:
            if s["disabled"]:
                st_label = f"[{COLOR_DANGER}]DISABLED[/{COLOR_DANGER}]"
            elif s["is_running"]:
                st_label = f"[{COLOR_SUCCESS}]RUNNING[/{COLOR_SUCCESS}]"
            else:
                st_label = f"[{COLOR_INFO}]READY[/{COLOR_INFO}]"

            endpoint = s["url"] if s.get("url") else f"{s['command']} {' '.join(s.get('args', []))}".strip()
            table.add_row(
                st_label,
                s["name"],
                s["transport"].upper(),
                endpoint,
                str(s["tool_count"]),
            )

        ui.console.print()
        ui.console.print(table)
        ui.console.print()


@mcp_app.command(name="add")
def add_cmd(
    name: str = typer.Argument(..., help="Unique identifier for the MCP server."),
    command_or_url: str = typer.Argument(..., help="Executable command (for stdio) or endpoint URL (for sse/http)."),
    args: list[str] = typer.Option([], "--arg", "-a", help="Arguments to pass to the stdio command."),
    transport: str = typer.Option("stdio", "--transport", "-t", help="Transport mode: 'stdio', 'sse', or 'http'."),
    env: list[str] = typer.Option([], "--env", "-e", help="Environment variables in KEY=VALUE format."),
    header: list[str] = typer.Option([], "--header", "-H", help="HTTP headers in KEY:VALUE format for sse/http."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Add or update an external MCP server definition in .codemind/mcp.json."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws)
    ui = TerminalUI(plain_mode=config.plain_mode)
    mcp_mgr = MCPManager(ws)

    env_dict: dict[str, str] = {}
    for item in env:
        if "=" in item:
            k, v = item.split("=", 1)
            env_dict[k.strip()] = v.strip()

    headers_dict: dict[str, str] = {}
    for item in header:
        if ":" in item:
            k, v = item.split(":", 1)
            headers_dict[k.strip()] = v.strip()

    t_mode = transport.lower().strip()
    if t_mode in ("http", "sse"):
        url = command_or_url
        cmd = None
        cmd_args = []
    else:
        url = None
        cmd = command_or_url
        cmd_args = args

    mcp_mgr.add_server(
        name=name,
        command=cmd,
        args=cmd_args,
        transport=t_mode,
        url=url,
        headers=headers_dict,
        env=env_dict,
    )
    ui.print_success(f"MCP server '{name}' registered ({t_mode.upper()}).")


@mcp_app.command(name="inspect")
def inspect_cmd(
    name: str = typer.Argument(..., help="Name of the MCP server to inspect."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Inspect server configuration, connection health, and discovered tools."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    mcp_mgr = MCPManager(ws)

    servers_cfg = mcp_mgr.load_config()
    if name not in servers_cfg.mcpServers:
        ui.print_error(f"MCP server '{name}' not found in .codemind/mcp.json.")
        raise typer.Exit(1)

    s_cfg = servers_cfg.mcpServers[name]

    if config.plain_mode:
        print(f"\nMCP Server: {name}")
        print(f"Transport: {s_cfg.transport.value.upper()}")
        if s_cfg.url:
            print(f"URL: {s_cfg.url}")
        if s_cfg.command:
            print(f"Command: {s_cfg.command} {' '.join(s_cfg.args)}")
        print(f"Disabled: {s_cfg.disabled}")
        print(f"CWD: {s_cfg.cwd}")
        if s_cfg.env:
            print(f"Environment: {', '.join(s_cfg.env.keys())}")
        print()
    else:
        lines = [
            f"[bold]Server Name:[/bold] {name}",
            f"[bold]Transport:[/bold] {s_cfg.transport.value.upper()}",
            f"[bold]Disabled:[/bold] {'[red]Yes[/red]' if s_cfg.disabled else '[green]No[/green]'}",
            f"[bold]Working Directory:[/bold] {s_cfg.cwd}",
        ]
        if s_cfg.url:
            lines.append(f"[bold]URL:[/bold] {s_cfg.url}")
        if s_cfg.command:
            lines.append(f"[bold]Command:[/bold] {s_cfg.command} {' '.join(s_cfg.args)}")
        if s_cfg.env:
            lines.append(f"[bold]Env Keys:[/bold] {', '.join(s_cfg.env.keys())}")

        panel = Panel("\n".join(lines), title=f"MCP Configuration: {name}", border_style=COLOR_ACCENT)
        ui.console.print()
        ui.console.print(panel)
        ui.console.print()


@mcp_app.command(name="test")
def test_cmd(
    name: str = typer.Argument(..., help="Name of the MCP server to test."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Test live connectivity, initialization handshake, and tool discovery."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    mcp_mgr = MCPManager(ws)

    ui.print_info(f"Testing MCP server '{name}'...")
    res = asyncio.run(mcp_mgr.test_server(name))

    if res.get("healthy"):
        ui.print_success(f"PASSED: Connected to MCP server '{name}'. Discovered {res.get('tool_count', 0)} tool(s): {', '.join(res.get('tools', [])) or '(none)'}")
    else:
        ui.print_error(f"FAILED: Connection to MCP server '{name}' failed: {res.get('error', 'unknown error')}")


@mcp_app.command(name="remove")
def remove_cmd(
    name: str = typer.Argument(..., help="Name of the MCP server to remove."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Remove an MCP server from configuration."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws)
    ui = TerminalUI(plain_mode=config.plain_mode)
    mcp_mgr = MCPManager(ws)

    if mcp_mgr.remove_server(name):
        ui.print_success(f"MCP server '{name}' removed from .codemind/mcp.json.")
    else:
        ui.print_error(f"MCP server '{name}' was not found.")
