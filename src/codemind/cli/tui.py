"""CodeMind Professional Terminal UI (TUI) Engine.

Provides a clean, minimalist, dark-themed terminal interface with:
- Visual hierarchy and restrained CodeMind branding.
- Structured task progress tracking and phase badges.
- Formatted tool action callouts without raw dictionary dumps.
- Turn-budget and context utilization meters.
- Safe interactive REPL loop with continuation, pause, and cancellation support.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from codemind import __brand_mark__, __version__
from codemind.cli.branding import (
    COLOR_ACCENT,
    COLOR_DANGER,
    COLOR_INFO,
    COLOR_MUTED,
    COLOR_SUCCESS,
    COLOR_WARNING,
    PLAIN_BRAND_MARK,
    TAGLINE,
)
from codemind.planning.task import TaskItem, TaskPlan, TaskStatus
from codemind.verification.reporter import CompletionStatus, HonestCompletionReport

# Color palette: Dark, muted, professional terminal theme
THEME_BG = "#1A1B26"
THEME_BORDER = "#3B4252"
THEME_MUTED_TEXT = "#7B8496"
THEME_TEXT = "#D8DEE9"
THEME_ACCENT = "#FF9E3B"
THEME_SUCCESS = "#4EBA6F"
THEME_WARNING = "#E5C07B"
THEME_DANGER = "#E06C75"
THEME_INFO = "#61AFEF"


class CodeMindTUI:
    """Polished terminal user interface for interactive companion sessions."""

    def __init__(self, console: Console | None = None, plain_mode: bool = False):
        self.plain_mode = plain_mode
        self.console = console or Console(no_color=plain_mode, highlight=not plain_mode)

    def print_header(
        self,
        model_name: str,
        provider: str,
        workspace: str,
        permission_mode: str,
        turn_budget: int = 20,
    ) -> None:
        """Render the top CodeMind identity and environment status header."""
        if self.plain_mode:
            print("=" * 60)
            print(f"{PLAIN_BRAND_MARK} v{__version__} — {TAGLINE}")
            print(f"Model: {model_name} ({provider}) | Mode: {permission_mode} | Budget: {turn_budget} turns")
            print(f"Workspace: {workspace}")
            print("=" * 60 + "\n")
            return

        header_table = Table.grid(expand=True)
        header_table.add_column("Left", justify="left")
        header_table.add_column("Right", justify="right")

        left = Text()
        left.append(f"{__brand_mark__} ", style=f"bold {THEME_ACCENT}")
        left.append(f"v{__version__}", style=f"dim {THEME_MUTED_TEXT}")
        left.append(f"  •  {TAGLINE}", style=f"italic {THEME_MUTED_TEXT}")

        right = Text()
        right.append(f"Model: ", style="dim")
        right.append(f"{model_name} ", style=f"bold {THEME_INFO}")
        right.append(f"({provider})", style=f"dim {THEME_MUTED_TEXT}")

        header_table.add_row(left, right)

        sub_table = Table.grid(expand=True)
        sub_table.add_column("Left", justify="left")
        sub_table.add_column("Right", justify="right")

        ws_text = Text()
        ws_text.append("Workspace: ", style="dim")
        ws_text.append(str(workspace), style="white")

        mode_style = THEME_SUCCESS if permission_mode == "supervised" else THEME_WARNING
        status_text = Text()
        status_text.append("Mode: ", style="dim")
        status_text.append(f"{permission_mode}  ", style=f"bold {mode_style}")
        status_text.append(f"Turn Budget: ", style="dim")
        status_text.append(f"{turn_budget} max", style="cyan")

        sub_table.add_row(ws_text, status_text)

        panel_content = Table.grid(padding=(0, 0))
        panel_content.add_column()
        panel_content.add_row(header_table)
        panel_content.add_row(Text(""))
        panel_content.add_row(sub_table)

        self.console.print(
            Panel(
                panel_content,
                border_style=THEME_BORDER,
                padding=(1, 2),
            )
        )

    def print_budget_meter(self, turn: int, max_turns: int, tool_calls: int, max_tool_calls: int) -> None:
        """Render a compact turn and tool-call budget gauge."""
        if self.plain_mode:
            print(f"[Budget: Turn {turn}/{max_turns} | Tools: {tool_calls}/{max_tool_calls}]")
            return

        pct = min(1.0, turn / max(1, max_turns))
        filled_bars = int(pct * 10)
        empty_bars = 10 - filled_bars
        bar_color = THEME_SUCCESS if pct < 0.7 else (THEME_WARNING if pct < 0.9 else THEME_DANGER)

        gauge = Text()
        gauge.append("Turns: ", style="dim")
        gauge.append(f"{turn}/{max_turns} ", style="bold white")
        gauge.append("[", style="dim")
        gauge.append("■" * filled_bars, style=bar_color)
        gauge.append("·" * empty_bars, style="dim")
        gauge.append("]  ", style="dim")
        gauge.append(f"Tools: ", style="dim")
        gauge.append(f"{tool_calls}/{max_tool_calls}", style="cyan" if tool_calls < max_tool_calls else "red")

        self.console.print(gauge)

    def print_task_lifecycle(self, phase: str, details: str = "") -> None:
        """Display an explicit task lifecycle transition badge."""
        if self.plain_mode:
            detail_str = f" - {details}" if details else ""
            print(f"[{phase.upper()}]{detail_str}")
            return

        badge_colors = {
            "PLANNING": THEME_INFO,
            "EXECUTING": THEME_ACCENT,
            "WAITING FOR APPROVAL": THEME_WARNING,
            "TESTING": THEME_INFO,
            "PAUSED": THEME_WARNING,
            "FAILED": THEME_DANGER,
            "COMPLETED": THEME_SUCCESS,
        }
        color = badge_colors.get(phase.upper(), THEME_MUTED_TEXT)

        line = Text()
        line.append("● ", style=color)
        line.append(f"{phase.upper()}", style=f"bold {color}")
        if details:
            line.append(f"  {details}", style="dim")

        self.console.print(line)

    def print_plan_progress(self, tasks: list[dict[str, Any]] | list[TaskItem]) -> None:
        """Render structured task plan with clean state indicators."""
        if not tasks:
            return

        if self.plain_mode:
            print("\n--- Task Plan ---")
            for t in tasks:
                if isinstance(t, dict):
                    status = t.get("status", "pending")
                    tid = t.get("id", "")
                    title = t.get("title", "")
                else:
                    status = t.status.value if hasattr(t.status, "value") else str(t.status)
                    tid = t.id
                    title = t.title

                icon = {
                    "completed": "[✓]",
                    "running": "[●]",
                    "in_progress": "[●]",
                    "paused": "[⏸]",
                    "pending": "[○]",
                    "failed": "[✗]",
                    "blocked": "[!]",
                    "cancelled": "[-]",
                    "skipped": "[-]",
                }.get(status, "[ ]")
                print(f"  {icon} {tid:8} : {title} ({status})")
            print("-----------------\n")
            return

        table = Table(
            show_header=True,
            header_style=f"bold {THEME_MUTED_TEXT}",
            border_style=THEME_BORDER,
            box=None,
            padding=(0, 1),
            expand=True,
        )
        table.add_column("State", width=14, justify="left")
        table.add_column("ID", width=10, style=f"dim {THEME_MUTED_TEXT}")
        table.add_column("Task Objective", justify="left")

        for t in tasks:
            if isinstance(t, dict):
                status = t.get("status", "pending")
                tid = t.get("id", "")
                title = t.get("title", "")
            else:
                status = t.status.value if hasattr(t.status, "value") else str(t.status)
                tid = t.id
                title = t.title

            status_cell = Text()
            if status == "completed":
                status_cell.append("✓ Done", style=f"bold {THEME_SUCCESS}")
            elif status in ("running", "in_progress"):
                status_cell.append("● Running", style=f"bold {THEME_ACCENT}")
            elif status == "paused":
                status_cell.append("⏸ Paused", style=f"bold {THEME_WARNING}")
            elif status == "failed":
                status_cell.append("✗ Failed", style=f"bold {THEME_DANGER}")
            elif status == "blocked":
                status_cell.append("! Blocked", style=f"bold {THEME_WARNING}")
            elif status in ("cancelled", "skipped"):
                status_cell.append("- Skipped", style=f"dim {THEME_MUTED_TEXT}")
            else:
                status_cell.append("○ Pending", style=f"dim {THEME_MUTED_TEXT}")

            table.add_row(status_cell, tid, title)

        self.console.print(
            Panel(
                table,
                title=f"[bold {THEME_ACCENT}]Structured Execution Plan[/bold {THEME_ACCENT}]",
                border_style=THEME_BORDER,
                padding=(0, 1),
            )
        )

    def print_tool_activity(self, tool_name: str, reason: str, args: dict[str, Any]) -> None:
        """Render formatted tool action callout without raw dictionary dumps."""
        if self.plain_mode:
            print(f"\n[Action: {tool_name}]")
            if reason:
                print(f"  Reason: {reason}")
            # Format arguments cleanly
            for k, v in args.items():
                v_str = str(v)
                if len(v_str) > 80:
                    v_str = v_str[:77] + "..."
                print(f"  • {k}: {v_str}")
            return

        content = Text()
        content.append(f"Action: ", style="dim")
        content.append(f"{tool_name}\n", style=f"bold {THEME_ACCENT}")

        if reason:
            content.append("Reason: ", style="dim")
            content.append(f"{reason}\n", style="italic white")

        # Format key arguments cleanly
        content.append("Parameters:\n", style="dim")
        for k, v in args.items():
            content.append(f"  • {k}: ", style="dim")
            if k in ("content", "patch", "text") and isinstance(v, str):
                lines = v.strip().splitlines()
                content.append(f"({len(lines)} lines, {len(v)} bytes)\n", style=THEME_INFO)
            else:
                v_str = str(v)
                if len(v_str) > 90:
                    v_str = v_str[:87] + "..."
                content.append(f"{v_str}\n", style="white")

        self.console.print(
            Panel(
                content,
                title=f"[{THEME_INFO}]Agent Tool Invocation[/{THEME_INFO}]",
                border_style=THEME_BORDER,
                padding=(0, 2),
            )
        )

    def print_tool_observation(self, ok: bool, output: str, truncated: bool = False) -> None:
        """Render tool execution observation."""
        if self.plain_mode:
            status = "OK" if ok else "ERROR"
            trunc = " (truncated)" if truncated else ""
            print(f"Observation [{status}]{trunc}: {output.strip()}\n")
            return

        color = THEME_SUCCESS if ok else THEME_DANGER
        icon = "✓" if ok else "✗"
        title = f"[{color}]{icon} Observation[/{color}]"
        if truncated:
            title += " [dim](output truncated)[/dim]"

        clean_output = output.strip() if output.strip() else "(no output)"
        self.console.print(
            Panel(
                Text(clean_output, style="white"),
                title=title,
                border_style=color,
                padding=(0, 1),
            )
        )

    def print_approval_card(self, action_description: str, command_or_target: str) -> None:
        """Render a prominent security confirmation panel."""
        if self.plain_mode:
            print(f"\n[APPROVAL REQUIRED - Supervised Mode]")
            print(f"Action: {action_description}")
            print(f"Target: {command_or_target}")
            return

        card = Text()
        card.append("A security-sensitive operation requires your approval:\n\n", style="white")
        card.append("Operation : ", style="dim")
        card.append(f"{action_description}\n", style=f"bold {THEME_WARNING}")
        card.append("Target    : ", style="dim")
        card.append(f"{command_or_target}\n\n", style=f"bold {THEME_TEXT}")
        card.append("Permission: supervised mode active", style="dim italic")

        self.console.print(
            Panel(
                card,
                title=f"[bold {THEME_WARNING}]⚠ Authorization Gate[/bold {THEME_WARNING}]",
                border_style=THEME_WARNING,
                padding=(1, 2),
            )
        )

    def print_verification_card(self, report: HonestCompletionReport, workspace_root: Path | None = None) -> None:
        """Render honest verification results card."""
        status_label, verified = report.evaluate_status(workspace_root)

        if self.plain_mode:
            print(report.format_summary(workspace_root))
            return

        card = Table.grid(padding=(0, 1), expand=True)
        card.add_column("Key", width=18, style="dim")
        card.add_column("Value", justify="left")

        # Status badge
        badge_color = THEME_SUCCESS if verified else (THEME_WARNING if "PAUSED" in status_label else THEME_DANGER)
        card.add_row("Verified Status", Text(status_label, style=f"bold {badge_color}"))

        if report.files_created:
            created_str = ", ".join(report.files_created)
            card.add_row("Files Created", Text(f"+ {created_str}", style=THEME_SUCCESS))

        if report.files_modified:
            mod_str = ", ".join(report.files_modified)
            card.add_row("Files Modified", Text(f"* {mod_str}", style=THEME_INFO))

        if report.missing_files:
            missing_str = ", ".join(report.missing_files)
            card.add_row("Missing Files", Text(f"! {missing_str}", style=f"bold {THEME_DANGER}"))

        if report.checks:
            check_lines = Text()
            for c in report.checks:
                s = "✓ PASS" if c.passed else f"✗ FAIL (code {c.exit_code})"
                col = THEME_SUCCESS if c.passed else THEME_DANGER
                check_lines.append(f"{s} ", style=f"bold {col}")
                check_lines.append(f"{c.command}\n", style="white")
            card.add_row("Verification Checks", check_lines)
        else:
            card.add_row("Verification Checks", Text("None executed", style="dim"))

        if report.unverified_notes:
            unv = Text("\n".join(f"• {u}" for u in report.unverified_notes), style=THEME_WARNING)
            card.add_row("Caveats", unv)

        title_style = f"bold {badge_color}"
        self.console.print(
            Panel(
                card,
                title=f"[{title_style}]Verification & Integrity Report[/{title_style}]",
                border_style=badge_color,
                padding=(1, 2),
            )
        )

    def print_task_paused(self, turns: int, max_turns: int) -> None:
        """Render explicit task paused notification."""
        if self.plain_mode:
            print(f"\n[PAUSED] Task paused at turn limit ({turns}/{max_turns}).")
            print("Type 'continue' to resume or enter a new request.\n")
            return

        text = Text()
        text.append(f"Task paused: reached turn budget limit ({turns}/{max_turns} turns).\n", style=f"bold {THEME_WARNING}")
        text.append("All work, task DAG positions, and checkpoints have been safely preserved.\n\n", style="dim")
        text.append("Options:\n", style="bold white")
        text.append("  • Type ", style="dim")
        text.append("continue", style=f"bold {THEME_SUCCESS}")
        text.append(" to resume execution with a fresh turn budget.\n", style="dim")
        text.append("  • Type a new instruction to start an independent task.\n", style="dim")
        text.append("  • Type ", style="dim")
        text.append("status", style="cyan")
        text.append(" or ", style="dim")
        text.append("plan", style="cyan")
        text.append(" to inspect current state.\n", style="dim")

        self.console.print(
            Panel(
                text,
                title=f"[bold {THEME_WARNING}]⏸ Task Paused[/bold {THEME_WARNING}]",
                border_style=THEME_WARNING,
                padding=(1, 2),
            )
        )
