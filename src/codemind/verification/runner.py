"""Test runner discovery and verification execution."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codemind.security.sandbox import WorkspaceSandbox


class TestCheckResult(BaseModel):
    command: str
    passed: bool
    exit_code: int
    passed_count: int = 0
    failed_count: int = 0
    details: str = ""
    truncated: bool = False


class VerificationRunner:
    """Discovers and executes verification test commands inside the workspace."""

    def __init__(self, workspace_root: Path, sandbox: WorkspaceSandbox):
        self.workspace_root = workspace_root.resolve()
        self.sandbox = sandbox

    def discover_test_command(self) -> str | None:
        """Heuristically identify the primary test runner command for this repository."""
        # 1. Custom runner in repository root
        if (self.workspace_root / "run_tests.py").is_file():
            return "python3 run_tests.py"

        # 2. Python projects
        if (self.workspace_root / "pyproject.toml").is_file() or (self.workspace_root / "setup.py").is_file():
            if (self.workspace_root / "tests").is_dir():
                if (self.workspace_root / "src").is_dir():
                    return "PYTHONPATH=src:. python3 -m unittest discover -s tests"
                return "python3 -m unittest discover -s tests"

        # 3. Node projects
        if (self.workspace_root / "package.json").is_file():
            return "npm test"

        # 4. Rust projects
        if (self.workspace_root / "Cargo.toml").is_file():
            return "cargo test"

        # 5. Go projects
        if (self.workspace_root / "go.mod").is_file():
            return "go test ./..."

        return None

    async def run_check(self, command: str | None = None, timeout_seconds: int = 60) -> TestCheckResult:
        """Execute test command and parse outcomes."""
        cmd = command or self.discover_test_command()
        if not cmd:
            return TestCheckResult(
                command="None",
                passed=False,
                exit_code=-1,
                details="No automated test suite discovered in this project.",
            )

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=str(self.workspace_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=float(timeout_seconds),
            )
            exit_code = proc.returncode or 0
            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")
            combined = stdout_str + ("\n" + stderr_str if stderr_str else "")

            passed = exit_code == 0
            passed_count, failed_count = self._parse_counts(combined)

            return TestCheckResult(
                command=cmd,
                passed=passed,
                exit_code=exit_code,
                passed_count=passed_count,
                failed_count=failed_count,
                details=combined[:2000],
            )
        except asyncio.TimeoutError:
            return TestCheckResult(
                command=cmd,
                passed=False,
                exit_code=-1,
                details=f"Verification command timed out after {timeout_seconds} seconds.",
            )
        except Exception as ex:
            return TestCheckResult(
                command=cmd,
                passed=False,
                exit_code=-1,
                details=f"Failed to execute check '{cmd}': {ex}",
            )

    def _parse_counts(self, text: str) -> tuple[int, int]:
        """Attempt to extract passed/failed counts from unittest/pytest output."""
        passed = 0
        failed = 0

        # Unittest style: "Ran 12 tests in 0.05s\nOK"
        ran_match = re.search(r"Ran (\d+) tests? in", text)
        if ran_match:
            total = int(ran_match.group(1))
            fail_match = re.search(r"FAILED \((?:failures=(\d+))?(?:, )?(?:errors=(\d+))?\)", text)
            if fail_match:
                f_count = int(fail_match.group(1) or 0) + int(fail_match.group(2) or 0)
                failed = f_count
                passed = max(0, total - failed)
            elif "OK" in text:
                passed = total
                failed = 0
            return passed, failed

        # Pytest style: "12 passed, 2 failed in 0.5s"
        py_pass = re.search(r"(\d+) passed", text)
        py_fail = re.search(r"(\d+) failed", text)
        if py_pass:
            passed = int(py_pass.group(1))
        if py_fail:
            failed = int(py_fail.group(1))

        return passed, failed
