"""Honest completion report generator.

Authoritative completion record reflecting actual system operations, disk state,
and verification tests without false success claims or stale artifacts.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from codemind.verification.runner import TestCheckResult


class CompletionStatus(str, Enum):
    VERIFIED_SUCCESS = "VERIFIED SUCCESS"
    COMPLETED_UNVERIFIED = "COMPLETED WITH UNVERIFIED WORK"
    PAUSED = "PAUSED (TURN LIMIT REACHED)"
    CANCELLED = "CANCELLED BY USER"
    FAILED = "FAILED"
    INCOMPLETE = "INCOMPLETE"


class HonestCompletionReport(BaseModel):
    """Authoritative completion record reflecting actual system operations and tests."""

    task_id: str = ""
    task_instruction: str = ""
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    commands_executed: list[str] = Field(default_factory=list)
    checks: list[TestCheckResult] = Field(default_factory=list)
    system_checks: list[TestCheckResult] = Field(default_factory=list)
    task_completed: bool = True
    is_paused: bool = False
    is_cancelled: bool = False
    missing_files: list[str] = Field(default_factory=list)
    verified: bool = False
    unverified_notes: list[str] = Field(default_factory=list)

    def evaluate_status(self, workspace_root: Path | None = None) -> tuple[str, bool]:
        """Strictly evaluate verified status against real disk evidence and task lifecycle."""
        if self.is_cancelled:
            self.verified = False
            return CompletionStatus.CANCELLED.value, False

        if self.is_paused:
            self.verified = False
            if "Turn limit reached" not in self.unverified_notes:
                self.unverified_notes.append("Task paused due to turn budget limit before full completion.")
            return CompletionStatus.PAUSED.value, False

        if not self.task_completed:
            self.verified = False
            return CompletionStatus.INCOMPLETE.value, False

        # Verify created files physically exist on disk
        if workspace_root:
            missing: list[str] = []
            for rel_or_abs in self.files_created:
                p = Path(rel_or_abs)
                full = p if p.is_absolute() else (workspace_root / p)
                if not full.is_file():
                    missing.append(str(rel_or_abs))
            if missing:
                self.missing_files = missing
                self.verified = False
                return f"{CompletionStatus.FAILED.value} (Missing expected files: {', '.join(missing)})", False

        # Verify test checks if any executed for this task
        if self.checks:
            failed_checks = [c for c in self.checks if not c.passed]
            if failed_checks:
                self.verified = False
                return f"{CompletionStatus.FAILED.value} ({len(failed_checks)} test check(s) failed)", False
            else:
                self.verified = True
                return CompletionStatus.VERIFIED_SUCCESS.value, True

        # Check if only system health checks were executed
        if self.system_checks:
            failed_sys = [c for c in self.system_checks if not c.passed]
            if failed_sys:
                self.verified = False
                return f"{CompletionStatus.FAILED.value} (System health check failed)", False
            else:
                # System checks passed, but user deliverable has mutations and no task-specific checks
                has_modifications = bool(self.files_created or self.files_modified)
                if has_modifications:
                    self.verified = False
                    if not any("CodeMind internal test suite" in n for n in self.unverified_notes):
                        self.unverified_notes.append(
                            "CodeMind internal test suite passed, but no automated test suite was discovered or executed for this specific user task deliverable."
                        )
                    return CompletionStatus.COMPLETED_UNVERIFIED.value, False

        # No test checks were executed
        has_modifications = bool(self.files_created or self.files_modified)
        if not has_modifications:
            self.verified = True
            return f"{CompletionStatus.VERIFIED_SUCCESS.value} (Read-only query)", True

        # Has mutations but no automated test checks
        self.verified = False
        return CompletionStatus.COMPLETED_UNVERIFIED.value, False

    def format_summary(self, workspace_root: Path | None = None) -> str:
        """Render a readable honest completion summary."""
        status_label, _ = self.evaluate_status(workspace_root)

        lines: list[str] = ["\n--- VERIFICATION & COMPLETION REPORT ---"]

        if self.task_id:
            lines.append(f"Task ID: {self.task_id}")

        if self.files_created:
            lines.append("Files Created:")
            for f in self.files_created:
                lines.append(f"  + {f}")

        if self.files_modified:
            lines.append("Files Modified:")
            for f in self.files_modified:
                lines.append(f"  * {f}")

        if not self.files_created and not self.files_modified:
            lines.append("Files Changed: None (Read-only task)")

        if self.missing_files:
            lines.append("Missing Expected Files:")
            for m in self.missing_files:
                lines.append(f"  ! {m} (not found on disk)")

        if self.checks:
            lines.append("\nVerification Checks Executed (Task):")
            for c in self.checks:
                status_str = "PASSED" if c.passed else f"FAILED (exit code {c.exit_code})"
                counts = f" [{c.passed_count} passed, {c.failed_count} failed]" if (c.passed_count or c.failed_count) else ""
                lines.append(f"  [{status_str}] {c.command}{counts}")
        else:
            lines.append("\nVerification Checks (Task): None executed")

        if self.system_checks:
            lines.append("\nSystem Health Checks Executed:")
            for sc in self.system_checks:
                status_str = "PASSED" if sc.passed else f"FAILED (exit code {sc.exit_code})"
                lines.append(f"  [{status_str}] {sc.command}")

        lines.append(f"\nFinal Verified Status: {status_label}")

        if self.unverified_notes:
            lines.append("Unverified Aspects:")
            for u in self.unverified_notes:
                lines.append(f"  ? {u}")

        lines.append("-" * 40)
        return "\n".join(lines)
