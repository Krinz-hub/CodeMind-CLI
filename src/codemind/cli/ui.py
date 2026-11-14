"""Terminal UI and formatted rendering for CodeMind CLI using Rich."""

from __future__ import annotations

import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from codemind.cli.branding import (
    BRAND_MARK,
    COLOR_ACCENT,
    COLOR_DANGER,
    COLOR_INFO,
    COLOR_MUTED,
    COLOR_SUCCESS,
    COLOR_WARNING,
    PLAIN_BRAND_MARK,
    TAGLINE,
)


class TerminalUI:
    """Encapsulates all terminal rendering with plain-mode support."""

    def __init__(self, plain_mode: bool = False):
        self.plain_mode = plain_mode
        self.console = Console(no_color=plain_mode, highlight=not plain_mode)

    def print_banner(
        self,
        model_name: str,
        provider: str,
        workspace: str,
        permission_mode: str,
    ) -> None:
        """Display the official CodeMind welcome banner."""
        if self.plain_mode:
            print(f"{PLAIN_BRAND_MARK}")
            print(f"{TAGLINE}\n")
            print(f"Model: {model_name}")
            print(f"Provider: {provider}")
            print(f"Workspace: {workspace}")
            print(f"Mode: {permission_mode}\n")
            print("Ready. Describe what you want to build.")
            print("-" * 50)
            return

        header_text = Text()
        header_text.append(f"{BRAND_MARK}\n", style=f"bold {COLOR_ACCENT}")
        header_text.append(f"{TAGLINE}\n\n", style=f"italic {COLOR_MUTED}")
        header_text.append("Model: ", style="bold")
        header_text.append(f"{model_name}\n", style=COLOR_INFO)
        header_text.append("Provider: ", style="bold")
        header_text.append(f"{provider}\n", style="cyan")
        header_text.append("Workspace: ", style="bold")
        header_text.append(f"{workspace}\n", style="magenta")
        header_text.append("Mode: ", style="bold")
        header_text.append(f"{permission_mode}", style="green" if permission_mode == "supervised" else "yellow")

        panel = Panel(
            header_text,
            border_style=COLOR_ACCENT,
            padding=(1, 2),
            title="[bold]▟●▙ CodeMind Companion[/bold]",
            subtitle="[italic]Milo is ready[/italic]",
        )
        self.console.print(panel)
        self.console.print("[dim]Ready. Describe what you want to build.[/dim]\n")

    def print_plan(self, tasks: list[dict[str, Any]]) -> None:
        """Render a structured task plan."""
        if not tasks:
            return

        if self.plain_mode:
            print("\n--- Plan ---")
            for t in tasks:
                status_icon = {
                    "completed": "[v]",
                    "in_progress": "[*]",
                    "pending": "[ ]",
                    "failed": "[x]",
                    "blocked": "[!]",
                    "skipped": "[-]",
                }.get(t.get("status", "pending"), "[ ]")
                print(f"{status_icon} {t.get('id', '')}: {t.get('title', '')}")
            print("-" * 12 + "\n")
            return

        table = Table(
            title="[bold #FF9E3B]Milo's Task Plan[/bold #FF9E3B]",
            border_style=COLOR_MUTED,
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Status", width=12, justify="center")
        table.add_column("ID", width=10, style="dim")
        table.add_column("Task Description", justify="left")

        for t in tasks:
            status = t.get("status", "pending")
            status_style = {
                "completed": (f"[{COLOR_SUCCESS}]✓ Done[/{COLOR_SUCCESS}]"),
                "in_progress": (f"[{COLOR_ACCENT}]→ Active[/{COLOR_ACCENT}]"),
                "pending": (f"[{COLOR_MUTED}]○ Pending[/{COLOR_MUTED}]"),
                "failed": (f"[{COLOR_DANGER}]✗ Failed[/{COLOR_DANGER}]"),
                "blocked": (f"[{COLOR_WARNING}]! Blocked[/{COLOR_WARNING}]"),
                "skipped": (f"[{COLOR_MUTED}]- Skipped[/{COLOR_MUTED}]"),
            }.get(status, status)

            table.add_row(status_style, t.get("id", ""), t.get("title", ""))

        self.console.print(table)
        self.console.print()

    def print_tool_call(self, tool_name: str, reason: str, args: dict[str, Any]) -> None:
        """Render tool invocation callout."""
        if self.plain_mode:
            print(f"\n[Tool: {tool_name}] Reason: {reason}")
            print(f"Arguments: {args}")
            return

        msg = Text()
        msg.append("Action: ", style="bold")
        msg.append(f"{tool_name}\n", style=f"bold {COLOR_ACCENT}")
        if reason:
            msg.append("Reason: ", style="bold dim")
            msg.append(f"{reason}\n", style="italic")
        arg_str = ", ".join(f"{k}={repr(v)}" for k, v in args.items())
        msg.append("Arguments: ", style="bold dim")
        msg.append(f"({arg_str})", style=COLOR_INFO)

        self.console.print(Panel(msg, border_style="dim", title=f"[{COLOR_ACCENT}]Milo Tool Request[/{COLOR_ACCENT}]"))

    def print_diff(self, file_path: str, diff_text: str) -> None:
        """Render unified diff with syntax highlighting."""
        if self.plain_mode:
            print(f"\n--- Diff for {file_path} ---")
            print(diff_text)
            print("-" * 30)
            return

        syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=True)
        self.console.print(
            Panel(
                syntax,
                title=f"[bold]Proposed Patch: {file_path}[/bold]",
                border_style=COLOR_WARNING,
            )
        )

    def print_command_preview(self, command: str, cwd: str) -> None:
        """Render shell command execution preview."""
        if self.plain_mode:
            print(f"\n[Execute Command]: {command} (in {cwd})")
            return

        cmd_text = Text()
        cmd_text.append("$ ", style="bold green")
        cmd_text.append(f"{command}\n", style="bold white")
        cmd_text.append(f"Working Directory: {cwd}", style="dim")

        self.console.print(
            Panel(
                cmd_text,
                title="[bold yellow]Command Preview[/bold yellow]",
                border_style="yellow",
            )
        )

    def request_approval(self, prompt: str) -> bool:
        """Prompt user for confirmation (y/N)."""
        suffix = " [y/N]: "
        if self.plain_mode:
            res = input(f"{prompt}{suffix}").strip().lower()
            return res in ["y", "yes"]

        self.console.print(f"[bold {COLOR_WARNING}]? {prompt}[/bold {COLOR_WARNING}]", end="")
        try:
            res = input(suffix).strip().lower()
            return res in ["y", "yes"]
        except (KeyboardInterrupt, EOFError):
            self.console.print()
            return False

    def print_tool_result(self, ok: bool, output: str, truncated: bool = False) -> None:
        """Render tool execution output."""
        if self.plain_mode:
            status = "OK" if ok else "ERROR"
            trunc = " (truncated)" if truncated else ""
            print(f"Result [{status}]{trunc}:\n{output}\n")
            return

        style = COLOR_SUCCESS if ok else COLOR_DANGER
        title = "Observation" if ok else "Tool Error"
        if truncated:
            title += " (output truncated)"

        display_text = output if output.strip() else "(empty output)"
        self.console.print(
            Panel(
                Text(display_text, style="white"),
                title=f"[{style}]{title}[/{style}]",
                border_style=style,
            )
        )

    def print_final_response(self, content: str, summary: list[str] | None = None) -> None:
        """Render the final answer from Milo."""
        if self.plain_mode:
            print("\n=== Final Response ===")
            print(content)
            if summary:
                print("\nSummary of actions:")
                for item in summary:
                    print(f" - {item}")
            print("=" * 22 + "\n")
            return

        msg = Text()
        msg.append(f"{content}\n\n", style="white")
        if summary:
            msg.append("Key Actions & Outcomes:\n", style=f"bold {COLOR_ACCENT}")
            for item in summary:
                msg.append(f"  • {item}\n", style="dim cyan")

        self.console.print(
            Panel(
                msg,
                title=f"[bold {COLOR_SUCCESS}]▟●▙ Task Completed[/bold {COLOR_SUCCESS}]",
                border_style=COLOR_SUCCESS,
                padding=(1, 2),
            )
        )

    def print_error(self, message: str) -> None:
        """Render error message."""
        if self.plain_mode:
            print(f"Error: {message}", file=sys.stderr)
            return
        self.console.print(f"[bold {COLOR_DANGER}]✗ Error:[/] {message}")

    def print_info(self, message: str) -> None:
        """Render informational note."""
        if self.plain_mode:
            print(f"Note: {message}")
            return
        self.console.print(f"[{COLOR_INFO}]ℹ[/] {message}")
