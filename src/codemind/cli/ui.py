"""Terminal UI and formatted rendering for CodeMind CLI using Rich.

Provides both standard logging callouts and the polished dark-themed CodeMind TUI.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from codemind import __brand_mark__, __version__
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
from codemind.cli.tui import CodeMindTUI
from codemind.planning.task import TaskItem, TaskPlan, TaskStatus
from codemind.verification.reporter import HonestCompletionReport


class TerminalUI:
    """Encapsulates all terminal rendering with plain-mode and rich TUI support."""

    def __init__(self, plain_mode: bool = False):
        self.plain_mode = plain_mode
        self.console = Console(no_color=plain_mode, highlight=not plain_mode)
        self.tui = CodeMindTUI(console=self.console, plain_mode=plain_mode)

    def print_banner(
        self,
        model_name: str,
        provider: str,
        workspace: str,
        permission_mode: str,
        turn_budget: int = 20,
    ) -> None:
        """Display the official CodeMind welcome header."""
        self.tui.print_header(
            model_name=model_name,
            provider=provider,
            workspace=workspace,
            permission_mode=permission_mode,
            turn_budget=turn_budget,
        )

    def print_budget_meter(self, turn: int, max_turns: int, tool_calls: int, max_tool_calls: int) -> None:
        """Render a compact turn and tool-call budget gauge."""
        self.tui.print_budget_meter(turn, max_turns, tool_calls, max_tool_calls)

    def print_task_lifecycle(self, phase: str, details: str = "") -> None:
        """Display an explicit task lifecycle transition badge."""
        self.tui.print_task_lifecycle(phase, details)

    def print_task_paused(self, turns: int, max_turns: int) -> None:
        """Render explicit task paused notification."""
        self.tui.print_task_paused(turns, max_turns)

    def print_verification_card(self, report: HonestCompletionReport, workspace_root: Path | None = None) -> None:
        """Render honest verification results card."""
        self.tui.print_verification_card(report, workspace_root)

    def print_plan(self, tasks: list[dict[str, Any]] | list[TaskItem]) -> None:
        """Render a structured task plan with clean state indicators."""
        self.tui.print_plan_progress(tasks)

    def print_tool_call(self, tool_name: str, reason: str, args: dict[str, Any]) -> None:
        """Render tool invocation callout without raw dictionary dumps."""
        self.tui.print_tool_activity(tool_name, reason, args)

    def print_tool_result(self, ok: bool, output: str, truncated: bool = False) -> None:
        """Render tool execution output."""
        self.tui.print_tool_observation(ok, output, truncated)

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

    def request_approval(self, prompt: str, target: str = "") -> bool:
        """Prompt user for confirmation (y/N) with clean authorization panel."""
        suffix = " [y/N]: "
        if self.plain_mode:
            res = input(f"{prompt} ({target}){suffix}" if target else f"{prompt}{suffix}").strip().lower()
            return res in ["y", "yes"]

        self.tui.print_approval_card(prompt, target or "workspace action")
        try:
            self.console.print(f"[bold {COLOR_WARNING}]Approve action?{suffix}[/bold {COLOR_WARNING}]", end="")
            res = input().strip().lower()
            return res in ["y", "yes"]
        except (KeyboardInterrupt, EOFError):
            self.console.print()
            return False

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
                title="[bold cyan]▟●▙ Milo Engineering Response[/bold cyan]",
                border_style=COLOR_ACCENT,
                padding=(1, 2),
            )
        )

    def print_info(self, text: str) -> None:
        if self.plain_mode:
            print(f"Note: {text}")
        else:
            self.console.print(f"[{COLOR_INFO}]ℹ[/] [dim]{text}[/dim]")

    def print_warning(self, text: str) -> None:
        if self.plain_mode:
            print(f"Warning: {text}")
        else:
            self.console.print(f"[{COLOR_WARNING}]![/] [{COLOR_WARNING}]{text}[/{COLOR_WARNING}]")

    def print_error(self, text: str) -> None:
        if self.plain_mode:
            print(f"Error: {text}", file=sys.stderr)
        else:
            self.console.print(f"[{COLOR_DANGER}]✗[/] [{COLOR_DANGER}]{text}[/{COLOR_DANGER}]")

    def print_success(self, text: str) -> None:
        if self.plain_mode:
            print(f"Success: {text}")
        else:
            self.console.print(f"[{COLOR_SUCCESS}]✓[/] [{COLOR_SUCCESS}]{text}[/{COLOR_SUCCESS}]")
