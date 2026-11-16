"""Reliability regression tests for completion invariants (REL-01, REL-02, REL-03)."""

import unittest
from pathlib import Path

from codemind.security.sandbox import WorkspaceSandbox
from codemind.verification.reporter import CompletionStatus, HonestCompletionReport
from codemind.verification.runner import TestCheckResult, VerificationRunner
from tests.base import BaseAgentTestCase


class TestCompletionInvariants(BaseAgentTestCase):
    def test_rel_01_paused_task_cannot_claim_success_even_with_passing_checks(self) -> None:
        """REL-01: A task paused at turn limit must evaluate to PAUSED and verified=False,

        regardless of whether unit test checks passed.
        """
        passing_check = TestCheckResult(
            command="python3 run_tests.py",
            passed=True,
            exit_code=0,
            passed_count=123,
            failed_count=0,
            details="All tests passed",
        )

        report = HonestCompletionReport(
            task_id="task-test-paused",
            task_instruction="Make me a portfolio using React",
            files_created=["src/App.jsx"],
            files_modified=[],
            task_completed=False,
            is_paused=True,
            is_cancelled=False,
            checks=[passing_check],
        )

        status_label, verified = report.evaluate_status(self.workspace_root)
        self.assertFalse(verified, "Invariant violation: Paused task was marked verified=True")
        self.assertEqual(status_label, CompletionStatus.PAUSED.value)
        self.assertNotIn("VERIFIED SUCCESS", status_label)

    def test_rel_02_missing_created_files_fails_task(self) -> None:
        """REL-02: If a model claims to have created files but they do not exist on disk,

        the report must evaluate to FAILED with missing files listed.
        """
        report = HonestCompletionReport(
            task_id="task-test-missing",
            task_instruction="Build calculator",
            files_created=["src/calc.py", "src/missing_component.py"],
            task_completed=True,
            is_paused=False,
            is_cancelled=False,
        )

        # Create one file, leave the other missing
        self.create_file("src/calc.py", "def add(a, b): return a + b")

        status_label, verified = report.evaluate_status(self.workspace_root)
        self.assertFalse(verified)
        self.assertIn("FAILED", status_label)
        self.assertIn("missing_component.py", status_label)
        self.assertIn("src/missing_component.py", report.missing_files)

    def test_rel_03_root_tests_not_conflated_with_user_deliverable(self) -> None:
        """REL-03: In a repo containing CodeMind's own run_tests.py, modifying user documents

        must NOT trigger root run_tests.py as user-task verification.
        """
        # Emulate CodeMind's root structure inside test workspace
        self.create_file("src/codemind/__init__.py", "# CodeMind package")
        self.create_file("run_tests.py", "print('CodeMind internal tests')")

        runner = VerificationRunner(self.workspace_root, self.sandbox)

        # User deliverable is in documents/portfolio
        user_files = ["documents/portfolio/index.html", "documents/portfolio/App.jsx"]
        test_cmd = runner.discover_test_command(changed_files=user_files)

        # Invariant: Must NOT return CodeMind's root run_tests.py
        self.assertIsNone(
            test_cmd,
            "Invariant violation: CodeMind's internal test runner was conflated with user deliverable!",
        )

    def test_system_checks_cannot_falsely_verify_user_deliverable(self) -> None:
        """Passing system_checks must NOT mark a mutated user deliverable as VERIFIED SUCCESS."""
        system_check = TestCheckResult(
            command="python3 run_tests.py",
            passed=True,
            exit_code=0,
            details="Internal CodeMind tests pass",
        )

        self.create_file("documents/portfolio/index.html", "<html></html>")

        report = HonestCompletionReport(
            task_id="task-portfolio",
            task_instruction="Make portfolio",
            files_created=["documents/portfolio/index.html"],
            task_completed=True,
            is_paused=False,
            system_checks=[system_check],
            checks=[],  # No user task tests
        )

        status_label, verified = report.evaluate_status(self.workspace_root)
        self.assertFalse(verified, "System health checks must not verify user deliverable")
        self.assertEqual(status_label, CompletionStatus.COMPLETED_UNVERIFIED.value)
        self.assertIn("CodeMind internal test suite passed", "\n".join(report.unverified_notes))


if __name__ == "__main__":
    unittest.main()
