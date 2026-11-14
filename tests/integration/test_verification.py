"""Integration tests for automated test discovery and verification reporting."""

import asyncio

from codemind.verification.reporter import HonestCompletionReport
from codemind.verification.runner import VerificationRunner
from tests.base import BaseAgentTestCase


class TestVerificationIntegration(BaseAgentTestCase):
    def test_run_check_and_generate_report(self) -> None:
        # Create a real python test inside test workspace
        self.create_file(
            "tests/test_math.py",
            "import unittest\n\nclass MathTest(unittest.TestCase):\n    def test_ok(self): self.assertEqual(1 + 1, 2)\n",
        )
        self.create_file("pyproject.toml", "[project]\nname = 'sample'\n")

        runner = VerificationRunner(self.workspace_root, self.sandbox)
        cmd = runner.discover_test_command()
        self.assertIsNotNone(cmd)

        result = asyncio.run(runner.run_check(cmd))
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)
        self.assertGreaterEqual(result.passed_count, 1)

        report = HonestCompletionReport(
            files_created=["tests/test_math.py"],
            checks=[result],
            verified=result.passed,
        )
        summary = report.format_summary()
        self.assertIn("VERIFIED SUCCESS", summary)
        self.assertIn("tests/test_math.py", summary)
