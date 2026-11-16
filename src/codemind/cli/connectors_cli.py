"""CLI commands for managing CodeMind's Universal App Connector ecosystem."""

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
from codemind.connectors.manager import ConnectorManager
from codemind.connectors.models import (
    ActionRiskLevel,
    AuthMethod,
    ConnectionStatus,
    ConnectorCredential,
)


connectors_app = typer.Typer(
    name="connectors",
    help="Discover, inspect, connect, and manage universal application connectors.",
    invoke_without_command=True,
)


@connectors_app.callback(invoke_without_command=True)
def connectors_default(
    ctx: typer.Context,
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Default handler for 'codemind connectors' - lists connectors and status."""
    if ctx.invoked_subcommand is None:
        list_cmd(plain=plain, workspace=workspace)


@connectors_app.command(name="list")
def list_cmd(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category (google, productivity, communication, media)."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """List available application connectors in the catalogue."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    manager = ConnectorManager(ws)

    manifests = manager.registry.list_connectors()
    if category:
        manifests = [m for m in manifests if m.category.lower() == category.lower()]

    if not manifests:
        ui.print_info("No connectors found matching category filter.")
        return

    statuses = {s["connector_id"]: s for s in manager.get_all_statuses()}

    if config.plain_mode:
        print("\nUniversal Application Connector Catalogue:")
        print(f"{'STATUS':<12} {'ID':<18} {'NAME':<16} {'CATEGORY':<14} {'AUTH':<10} {'ACTIONS':<8} {'DESCRIPTION':<35}")
        print("-" * 115)
        for m in manifests:
            st = statuses.get(m.connector_id, {})
            status_str = st.get("status", "disconnected").upper()
            print(f"{status_str:<12} {m.connector_id:<18} {m.name:<16} {m.category:<14} {m.auth_method.value:<10} {len(m.actions):<8} {m.description[:35]}")
        print()
    else:
        table = Table(
            title="Universal Application Connector Catalogue",
            show_header=True,
            header_style=f"bold {COLOR_ACCENT}",
            box=None,
            border_style=COLOR_MUTED,
        )
        table.add_column("Status", width=14)
        table.add_column("ID", style="bold", width=16)
        table.add_column("Name", width=16)
        table.add_column("Category", style=COLOR_INFO, width=14)
        table.add_column("Auth", width=12)
        table.add_column("Actions", justify="right", width=8)
        table.add_column("Description", style=COLOR_MUTED)

        for m in manifests:
            st = statuses.get(m.connector_id, {})
            c_status = st.get("status", "disconnected")
            if c_status == "connected":
                status_display = f"[{COLOR_SUCCESS}]CONNECTED[/{COLOR_SUCCESS}]"
            elif c_status == "expired":
                status_display = f"[{COLOR_WARNING}]EXPIRED[/{COLOR_WARNING}]"
            else:
                status_display = f"[{COLOR_MUTED}]DISCONNECTED[/{COLOR_MUTED}]"

            table.add_row(
                status_display,
                f"{m.icon} {m.connector_id}",
                m.name,
                m.category,
                m.auth_method.value,
                str(len(m.actions)),
                m.description,
            )

        ui.console.print()
        ui.console.print(table)
        ui.console.print()


@connectors_app.command(name="search")
def search_cmd(
    query: str = typer.Argument(..., help="Search keyword (connector name, capability, or action)."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Search catalogue connectors and their capabilities by keyword."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    manager = ConnectorManager(ws)

    results = manager.registry.search(query)
    if not results:
        ui.print_info(f"No connectors found matching '{query}'.")
        return

    statuses = {s["connector_id"]: s for s in manager.get_all_statuses()}

    if config.plain_mode:
        print(f"\nConnectors matching '{query}':")
        for m in results:
            st = statuses.get(m.connector_id, {})
            print(f"  • {m.connector_id} ({m.name}) [{st.get('status', 'disconnected').upper()}] - {m.description}")
        print()
    else:
        table = Table(
            title=f"Connectors Matching '{query}'",
            header_style=f"bold {COLOR_ACCENT}",
            box=None,
        )
        table.add_column("ID", style="bold", width=18)
        table.add_column("Name", width=16)
        table.add_column("Status", width=14)
        table.add_column("Matched Capabilities")

        for m in results:
            st = statuses.get(m.connector_id, {})
            matched_actions = [a.name for a in m.actions if query.lower() in a.name.lower() or query.lower() in a.description.lower()]
            caps_str = ", ".join(matched_actions) if matched_actions else m.description
            status_style = COLOR_SUCCESS if st.get("status") == "connected" else COLOR_MUTED

            table.add_row(
                f"{m.icon} {m.connector_id}",
                m.name,
                f"[{status_style}]{st.get('status', 'disconnected').upper()}[/{status_style}]",
                caps_str,
            )

        ui.console.print()
        ui.console.print(table)
        ui.console.print()


@connectors_app.command(name="inspect")
def inspect_cmd(
    connector_id: str = typer.Argument(..., help="Connector ID (e.g. gmail, youtube, notion)."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Inspect detailed manifest, actions, schemas, and policy of a connector."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    manager = ConnectorManager(ws)

    manifest = manager.registry.get_manifest(connector_id)
    if not manifest:
        ui.print_error(f"Connector '{connector_id}' not found in catalogue.")
        raise typer.Exit(1)

    adapter = manager.get_adapter(connector_id)
    status = adapter.get_status() if adapter else ConnectionStatus.DISCONNECTED
    policy = manager.permission_manager.get_policy(connector_id)

    if config.plain_mode:
        print(f"\nConnector: {manifest.name} ({manifest.connector_id})")
        print(f"Description: {manifest.description}")
        print(f"Category: {manifest.category} | Version: {manifest.version} | Icon: {manifest.icon}")
        print(f"Auth Method: {manifest.auth_method.value}")
        print(f"Status: {status.value.upper()}")
        print(f"Policy: Enabled={policy.enabled}, Read-Only={policy.read_only}")
        if manifest.required_scopes:
            print(f"Required Scopes: {', '.join(manifest.required_scopes)}")
        print("\nAvailable Actions:")
        for a in manifest.actions:
            props = list(a.args_schema.get("properties", {}).keys())
            print(f"  • {a.name} [{a.risk_level.value.upper()}]: {a.description}")
            if props:
                print(f"    Parameters: {', '.join(props)}")
        print()
    else:
        status_color = COLOR_SUCCESS if status == ConnectionStatus.CONNECTED else COLOR_MUTED
        info_lines = [
            f"[bold]Name:[/bold] {manifest.icon} {manifest.name} (v{manifest.version})",
            f"[bold]Category:[/bold] {manifest.category}",
            f"[bold]Description:[/bold] {manifest.description}",
            f"[bold]Authentication:[/bold] {manifest.auth_method.value}",
            f"[bold]Status:[/bold] [{status_color}]{status.value.upper()}[/{status_color}]",
            f"[bold]Policy:[/bold] Enabled={'[green]Yes[/green]' if policy.enabled else '[red]No[/red]'}, Read-Only={'[yellow]Yes[/yellow]' if policy.read_only else 'No'}",
        ]
        if manifest.required_scopes:
            info_lines.append(f"[bold]OAuth Scopes:[/bold] {', '.join(manifest.required_scopes)}")

        panel = Panel("\n".join(info_lines), title=f"Connector: {manifest.connector_id}", border_style=COLOR_ACCENT)
        ui.console.print()
        ui.console.print(panel)

        actions_table = Table(
            title=f"Exposed Capabilities ({len(manifest.actions)})",
            header_style=f"bold {COLOR_ACCENT}",
            box=None,
        )
        actions_table.add_column("Action", style="bold", width=22)
        actions_table.add_column("Risk Level", width=12)
        actions_table.add_column("Parameters", style=COLOR_INFO, width=28)
        actions_table.add_column("Description", style=COLOR_MUTED)

        for a in manifest.actions:
            risk_color = (
                COLOR_DANGER if a.risk_level == ActionRiskLevel.SENSITIVE
                else (COLOR_WARNING if a.risk_level == ActionRiskLevel.WRITE else COLOR_SUCCESS)
            )
            params = list(a.args_schema.get("properties", {}).keys())
            reqs = a.args_schema.get("required", [])
            param_str = ", ".join(f"{p}*" if p in reqs else p for p in params) or "(none)"

            actions_table.add_row(
                a.name,
                f"[{risk_color}]{a.risk_level.value.upper()}[/{risk_color}]",
                param_str,
                a.description,
            )

        ui.console.print()
        ui.console.print(actions_table)
        ui.console.print()


@connectors_app.command(name="connect")
def connect_cmd(
    connector_id: str = typer.Argument(..., help="Connector ID (e.g. gmail, youtube, discord, slack, notion, spotify)."),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Direct API key, bot token, or access token."),
    refresh_token: Optional[str] = typer.Option(None, "--refresh-token", help="OAuth refresh token."),
    client_id: Optional[str] = typer.Option(None, "--client-id", help="OAuth Client ID."),
    client_secret: Optional[str] = typer.Option(None, "--client-secret", help="OAuth Client Secret."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Connect an application by securely configuring and storing credentials in the vault."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    manager = ConnectorManager(ws)

    manifest = manager.registry.get_manifest(connector_id)
    if not manifest:
        ui.print_error(f"Unknown connector '{connector_id}'. Run 'codemind connectors list' to inspect available connectors.")
        raise typer.Exit(1)

    ui.print_info(f"Configuring connection for {manifest.icon} {manifest.name}...")

    access_tok = token
    r_tok = refresh_token
    c_id = client_id
    c_sec = client_secret

    if manifest.auth_method in (AuthMethod.BOT_TOKEN, AuthMethod.API_KEY):
        if not access_tok:
            prompt_label = "Bot Token" if manifest.auth_method == AuthMethod.BOT_TOKEN else "API Key / Integration Token"
            access_tok = typer.prompt(f"Enter {manifest.name} {prompt_label}", hide_input=True)

        cred = ConnectorCredential(
            connector_id=connector_id,
            auth_method=manifest.auth_method,
            access_token=access_tok,
        )
    elif manifest.auth_method == AuthMethod.OAUTH2:
        if not access_tok:
            ui.print_info(f"{manifest.name} utilizes OAuth 2.0 PKCE authentication.")
            ui.print_info("You can provide an existing OAuth Access/Refresh token or enter provider credentials.")
            access_tok = typer.prompt("OAuth Access Token (or press Enter to configure client keys)", default="", hide_input=True)
            if not access_tok:
                c_id = typer.prompt("OAuth Client ID", default="")
                c_sec = typer.prompt("OAuth Client Secret (optional for PKCE)", default="", hide_input=True)
                r_tok = typer.prompt("OAuth Refresh Token (if available)", default="", hide_input=True)

        cred = ConnectorCredential(
            connector_id=connector_id,
            auth_method=AuthMethod.OAUTH2,
            access_token=access_tok if access_tok else None,
            refresh_token=r_tok if r_tok else None,
            client_id=c_id if c_id else None,
            client_secret=c_sec if c_sec else None,
            scopes=manifest.required_scopes,
        )
    else:
        cred = ConnectorCredential(
            connector_id=connector_id,
            auth_method=AuthMethod.NONE,
        )

    manager.connect_credential(cred)
    ui.print_success(f"Credential securely encrypted and saved to CodeMind vault for '{connector_id}'.")

    # Run verification test
    ui.print_info("Verifying live connection health...")
    health = asyncio.run(manager.test_connection(connector_id))
    if health.healthy:
        ui.print_success(f"Verification successful: {health.message} ({health.latency_ms} ms)")
    else:
        ui.print_warning(f"Connection registered with warning: {health.message}")


@connectors_app.command(name="disconnect")
def disconnect_cmd(
    connector_id: str = typer.Argument(..., help="Connector ID to disconnect."),
    force: bool = typer.Option(False, "--force", "-f", help="Bypass confirmation prompt."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Disconnect an application and purge credentials from encrypted vault."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    manager = ConnectorManager(ws)

    if not force:
        confirm = typer.confirm(f"Are you sure you want to disconnect '{connector_id}' and purge its stored credentials?")
        if not confirm:
            ui.print_info("Disconnection cancelled.")
            return

    ok = manager.disconnect(connector_id)
    if ok:
        ui.print_success(f"Connector '{connector_id}' has been disconnected and credentials purged.")
    else:
        ui.print_info(f"No stored credentials found for '{connector_id}'.")


@connectors_app.command(name="status")
def status_cmd(
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Display connection and health status across all connectors."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    manager = ConnectorManager(ws)

    statuses = manager.get_all_statuses()

    if config.plain_mode:
        print("\nConnector Ecosystem Status:")
        print(f"{'CONNECTOR':<18} {'STATUS':<14} {'ENABLED':<10} {'MODE':<12} {'ACTIONS':<8}")
        print("-" * 65)
        for s in statuses:
            mode_str = "Read-Only" if s["read_only"] else "Read-Write"
            print(f"{s['connector_id']:<18} {s['status'].upper():<14} {'Yes' if s['is_enabled'] else 'No':<10} {mode_str:<12} {s['actions_count']:<8}")
        print()
    else:
        table = Table(
            title="Connector Ecosystem Live Status",
            header_style=f"bold {COLOR_ACCENT}",
            box=None,
        )
        table.add_column("Connector", style="bold", width=20)
        table.add_column("Status", width=14)
        table.add_column("Enabled", width=10)
        table.add_column("Mode", width=14)
        table.add_column("Actions", justify="right", width=8)

        for s in statuses:
            stat = s["status"]
            stat_color = COLOR_SUCCESS if stat == "connected" else (COLOR_WARNING if stat == "expired" else COLOR_MUTED)
            enabled_str = f"[{COLOR_SUCCESS}]Yes[/{COLOR_SUCCESS}]" if s["is_enabled"] else f"[{COLOR_DANGER}]No[/{COLOR_DANGER}]"
            mode_str = f"[{COLOR_WARNING}]Read-Only[/{COLOR_WARNING}]" if s["read_only"] else "Read-Write"

            table.add_row(
                f"{s['icon']} {s['connector_id']}",
                f"[{stat_color}]{stat.upper()}[/{stat_color}]",
                enabled_str,
                mode_str,
                str(s["actions_count"]),
            )

        ui.console.print()
        ui.console.print(table)
        ui.console.print()


@connectors_app.command(name="test")
def test_cmd(
    connector_id: str = typer.Argument(..., help="Connector ID to test (e.g. gmail, youtube, spotify)."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Perform real-time health and authentication check against provider API."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    manager = ConnectorManager(ws)

    ui.print_info(f"Testing connectivity and authentication for '{connector_id}'...")
    health = asyncio.run(manager.test_connection(connector_id))

    if health.healthy:
        ui.print_success(f"PASSED [{health.status.value.upper()}]: {health.message} ({health.latency_ms} ms)")
    else:
        ui.print_error(f"FAILED [{health.status.value.upper()}]: {health.message}")


@connectors_app.command(name="permissions")
def permissions_cmd(
    connector_id: str = typer.Argument(..., help="Connector ID to inspect or configure."),
    enable: Optional[bool] = typer.Option(None, "--enable/--disable", help="Enable or disable connector."),
    read_only: Optional[bool] = typer.Option(None, "--read-only/--read-write", help="Enforce read-only mode."),
    allow_action: Optional[str] = typer.Option(None, "--allow-action", help="Explicitly allow an action."),
    block_action: Optional[str] = typer.Option(None, "--block-action", help="Explicitly block an action."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Inspect and modify declarative permission policies for a connector."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    manager = ConnectorManager(ws)

    policy = manager.permission_manager.get_policy(connector_id)

    modified = False
    if enable is not None:
        policy.enabled = enable
        modified = True
    if read_only is not None:
        policy.read_only = read_only
        modified = True
    if allow_action:
        if allow_action not in policy.allowed_actions:
            policy.allowed_actions.append(allow_action)
        if allow_action in policy.blocked_actions:
            policy.blocked_actions.remove(allow_action)
        modified = True
    if block_action:
        if block_action not in policy.blocked_actions:
            policy.blocked_actions.append(block_action)
        if block_action in policy.allowed_actions:
            policy.allowed_actions.remove(block_action)
        modified = True

    if modified:
        manager.permission_manager.set_policy(connector_id, policy)
        ui.print_success(f"Updated permission policy for '{connector_id}'.")

    if config.plain_mode:
        print(f"\nPermission Policy for '{connector_id}':")
        print(f"  Enabled: {policy.enabled}")
        print(f"  Read-Only Mode: {policy.read_only}")
        print(f"  Supervised Actions: {', '.join(policy.supervised_actions) if policy.supervised_actions else '(all WRITE/SENSITIVE)'}")
        print(f"  Explicitly Allowed: {', '.join(policy.allowed_actions) if policy.allowed_actions else '(none)'}")
        print(f"  Explicitly Blocked: {', '.join(policy.blocked_actions) if policy.blocked_actions else '(none)'}\n")
    else:
        table = Table(title=f"Permission Policy: {connector_id}", box=None)
        table.add_column("Property", style="bold", width=22)
        table.add_column("Value")
        table.add_row("Enabled", f"[{COLOR_SUCCESS}]Yes[/{COLOR_SUCCESS}]" if policy.enabled else f"[{COLOR_DANGER}]No[/{COLOR_DANGER}]")
        table.add_row("Read-Only Mode", f"[{COLOR_WARNING}]Yes[/{COLOR_WARNING}]" if policy.read_only else "No")
        table.add_row("Explicitly Allowed", ", ".join(policy.allowed_actions) or "(default)")
        table.add_row("Explicitly Blocked", ", ".join(policy.blocked_actions) or "(none)")
        ui.console.print()
        ui.console.print(table)
        ui.console.print()


@connectors_app.command(name="tools")
def tools_cmd(
    connector_id: str = typer.Argument(..., help="Connector ID (e.g. youtube, gmail, drive)."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Inspect all agent tools exposed by a connector."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    manager = ConnectorManager(ws)

    manifest = manager.registry.get_manifest(connector_id)
    if not manifest:
        ui.print_error(f"Connector '{connector_id}' not found.")
        raise typer.Exit(1)

    adapter = manager.get_adapter(connector_id)
    tools = adapter.get_tools() if adapter else []

    if config.plain_mode:
        print(f"\nTools registered for '{connector_id}' ({len(tools)} total):")
        for t in tools:
            print(f"  • {t.name}: {t.description}")
        print()
    else:
        table = Table(
            title=f"Agent Tools for '{manifest.name}' ({len(tools)})",
            header_style=f"bold {COLOR_ACCENT}",
            box=None,
        )
        table.add_column("Tool Name", style="bold", width=28)
        table.add_column("Description", style=COLOR_MUTED)

        for t in tools:
            table.add_row(t.name, t.description)

        ui.console.print()
        ui.console.print(table)
        ui.console.print()


@connectors_app.command(name="logs")
def logs_cmd(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of recent log events to show."),
    connector: Optional[str] = typer.Option(None, "--connector", "-c", help="Filter logs by connector ID."),
    plain: bool = typer.Option(False, "--plain", "--no-color", help="Plain text output."),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Inspect sanitized connector audit trail and execution logs."""
    ws = Path(workspace or os.getcwd()).resolve()
    config = CodeMindConfig.load(workspace_dir=ws, overrides={"plain_mode": plain})
    ui = TerminalUI(plain_mode=config.plain_mode)
    manager = ConnectorManager(ws)

    records = manager.audit_logger.read_recent(limit=limit, connector_id=connector)
    if not records:
        ui.print_info("No connector audit log entries found.")
        return

    if config.plain_mode:
        print(f"\nConnector Audit Log (Last {len(records)} events):")
        print(f"{'TIMESTAMP':<20} {'CONNECTOR':<14} {'ACTION':<20} {'RISK':<10} {'STATUS':<10} {'LATENCY':<10}")
        print("-" * 90)
        for r in records:
            status_str = "SUCCESS" if r.get("success") else "FAILED"
            lat = f"{r.get('duration_ms', 0):.1f}ms"
            print(f"{r.get('timestamp', '')[:19]:<20} {r.get('connector_id', ''):<14} {r.get('action', ''):<20} {r.get('risk_level', '').upper():<10} {status_str:<10} {lat:<10}")
        print()
    else:
        table = Table(
            title=f"Connector Audit Log (Sanitized Trace)",
            header_style=f"bold {COLOR_ACCENT}",
            box=None,
        )
        table.add_column("Timestamp", width=20)
        table.add_column("Connector", style="bold", width=14)
        table.add_column("Action", width=22)
        table.add_column("Risk", width=10)
        table.add_column("Status", width=10)
        table.add_column("Latency", justify="right", width=10)

        for r in records:
            succ = r.get("success", False)
            status_style = COLOR_SUCCESS if succ else COLOR_DANGER
            status_label = f"[{status_style}]{'OK' if succ else 'FAIL'}[/{status_style}]"
            risk = r.get("risk_level", "read")
            risk_color = COLOR_DANGER if risk == "sensitive" else (COLOR_WARNING if risk == "write" else COLOR_SUCCESS)
            lat = f"{r.get('duration_ms', 0):.1f}ms"

            table.add_row(
                r.get("timestamp", "")[:19],
                r.get("connector_id", ""),
                r.get("action", ""),
                f"[{risk_color}]{risk.upper()}[/{risk_color}]",
                status_label,
                lat,
            )

        ui.console.print()
        ui.console.print(table)
        ui.console.print()
