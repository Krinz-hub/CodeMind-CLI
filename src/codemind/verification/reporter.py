"""Honest completion report generator."""

from __future__ import annotations

from pydantic import BaseModel, Field

from codemind.verification.runner import TestCheckResult


class HonestCompletionReport(BaseModel):
    """Authoritative completion record reflecting actual system operations and tests."""

    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    commands_executed: list[str] = Field(default_factory=list)
    checks: list[TestCheckResult] = Field(default_factory=list)
    verified: bool = False
    unverified_notes: list[str] = Field(default_factory=list)

    def format_summary(self) -> str:
        """Render a readable honest completion summary."""
        lines: list[str] = ["\n--- VERIFICATION & COMPLETION REPORT ---"]

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

        if self.checks:
            lines.append("\nVerification Checks Executed:")
            for c in self.checks:
                status_str = "PASSED" if c.passed else f"FAILED (exit code {c.exit_code})"
                counts = f" [{c.passed_count} passed, {c.failed_count} failed]" if (c.passed_count or c.failed_count) else ""
                lines.append(f"  [{status_str}] {c.command}{counts}")
        else:
            lines.append("\nVerification Checks: None executed")

        lines.append(f"\nFinal Verified Status: {'VERIFIED SUCCESS' if self.verified else 'COMPLETED WITH UNVERIFIED WORK'}")

        if self.unverified_notes:
            lines.append("Unverified Aspects:")
            for u in self.unverified_notes:
                lines.append(f"  ? {u}")

        lines.append("-" * 40)
        return "\n".join(lines)
