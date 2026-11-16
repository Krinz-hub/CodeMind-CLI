"""Intelligent Failure Classification and Recovery Engine."""

from __future__ import annotations

import re
from typing import Any

from codemind.orchestration.models import FailureCategory, RecoveryAction, RecoveryStrategy


class FailureClassifier:
    """Analyzes errors, outputs, and system state to determine structured recovery actions."""

    @classmethod
    def classify_tool_failure(
        cls,
        tool_name: str,
        output: str,
        exit_code: int | None = None,
        exception: Exception | None = None,
    ) -> RecoveryStrategy:
        """Classify a tool execution failure and generate an actionable recovery strategy."""
        out_lower = output.lower()

        # 1. Permission Denials (Authoritative invariant: Never retry permanently denied permissions)
        if (
            "permission denied" in out_lower
            or "access denied" in out_lower
            or "path traversal" in out_lower
            or "prohibited" in out_lower
            or "user denied" in out_lower
        ):
            return RecoveryStrategy(
                category=FailureCategory.PERMISSION_DENIED,
                action=RecoveryAction.TERMINATE_GRACEFULLY,
                max_attempts=0,
                retryable=False,
                message=f"Permission denied during '{tool_name}' execution.",
                guidance="Halt execution or request explicit user re-configuration. Do not retry denied actions.",
            )

        # 2. Timeout
        if "timed out" in out_lower or "timeout" in out_lower:
            return RecoveryStrategy(
                category=FailureCategory.TIMEOUT,
                action=RecoveryAction.RETRY_BACKOFF,
                max_attempts=1,
                backoff_seconds=2.0,
                message=f"Tool '{tool_name}' timed out.",
                guidance="Increase tool timeout budget or break the operation into smaller sub-tasks.",
            )

        # 3. Missing Dependencies
        if (
            "modulenotfounderror" in out_lower
            or "importerror: no module named" in out_lower
            or "cannot find module" in out_lower
            or "command not found" in out_lower
            or "no such file or directory: 'npm'" in out_lower
        ):
            pkg_match = re.search(r"no module named ['\"]([^'\"]+)['\"]", output, re.IGNORECASE)
            pkg = pkg_match.group(1) if pkg_match else "required dependency"
            return RecoveryStrategy(
                category=FailureCategory.MISSING_DEPENDENCY,
                action=RecoveryAction.REPLAN,
                max_attempts=2,
                message=f"Missing dependency identified: '{pkg}'.",
                guidance=f"Inspect project manifests and install or declare '{pkg}' before re-attempting.",
            )

        # 4. Build & Compilation Failures
        if (
            "syntaxerror" in out_lower
            or "indentationerror" in out_lower
            or "typeerror: compile" in out_lower
            or "error ts" in out_lower  # TypeScript compiler
            or "compilation error" in out_lower
        ):
            return RecoveryStrategy(
                category=FailureCategory.BUILD_FAILURE,
                action=RecoveryAction.BUILD_REPAIR,
                max_attempts=3,
                message="Build/Syntax compilation failure detected.",
                guidance="Inspect exact line numbers in compiler output and apply targeted syntax correction.",
            )

        # 5. Test Failures (Assertion errors, exit code != 0 from test runners)
        if (
            "assertionerror" in out_lower
            or "failed (failures=" in out_lower
            or "tests failed" in out_lower
            or "fail:" in out_lower
            or "assert " in out_lower
            or (tool_name == "run_command" and ("pytest" in out_lower or "unittest" in out_lower))
        ):
            return RecoveryStrategy(
                category=FailureCategory.TEST_FAILURE,
                action=RecoveryAction.TEST_DRIVEN_REPAIR,
                max_attempts=3,
                message="Automated test failure observed.",
                guidance="Analyze test traceback, identify root cause vs symptom, and patch implementation or test assumptions.",
            )

        # 6. Patch Mismatch & State Drift
        if "patch failed" in out_lower or "could not match target" in out_lower or "target not found" in out_lower:
            return RecoveryStrategy(
                category=FailureCategory.TOOL_EXECUTION_FAILURE,
                action=RecoveryAction.REFRESH_FILE_CONTEXT,
                max_attempts=2,
                message="Patch application failed due to target content mismatch.",
                guidance="Re-read the target file to refresh exact line content, then apply targeted patch.",
            )

        # 7. Uncertain Outcome (e.g. process terminated mid-execution)
        if "broken pipe" in out_lower or "interrupted" in out_lower or "connection reset" in out_lower:
            return RecoveryStrategy(
                category=FailureCategory.UNCERTAIN_OUTCOME,
                action=RecoveryAction.VERIFY_DISK_OUTCOME,
                max_attempts=1,
                message="Operation outcome uncertain due to process interruption.",
                guidance="Verify physical filesystem state before repeating operation to avoid duplicate mutation.",
            )

        # Default Generic Tool Failure
        return RecoveryStrategy(
            category=FailureCategory.TOOL_EXECUTION_FAILURE,
            action=RecoveryAction.RETRY_BACKOFF,
            max_attempts=2,
            backoff_seconds=1.0,
            message=f"Tool '{tool_name}' failed with code {exit_code or 1}.",
            guidance="Inspect tool error output and attempt alternative tool or revised arguments.",
        )

    @classmethod
    def classify_model_failure(cls, error_message: str) -> RecoveryStrategy:
        """Classify a model adapter generation failure."""
        err_lower = error_message.lower()
        if "context length" in err_lower or "token limit" in err_lower or "context window" in err_lower:
            return RecoveryStrategy(
                category=FailureCategory.CONTEXT_EXHAUSTION,
                action=RecoveryAction.REPLAN,
                max_attempts=2,
                message="Model context window exhausted.",
                guidance="Compact conversation history, prune tool observations, and re-inject core task state.",
            )
        return RecoveryStrategy(
            category=FailureCategory.MODEL_RESPONSE_FAILURE,
            action=RecoveryAction.RETRY_BACKOFF,
            max_attempts=3,
            backoff_seconds=1.5,
            message=f"Model communication error: {error_message}",
            guidance="Verify local Ollama service health and retry with exponential backoff.",
        )

    @classmethod
    def classify_protocol_failure(cls, validation_error: str) -> RecoveryStrategy:
        """Classify a malformed envelope response from model."""
        return RecoveryStrategy(
            category=FailureCategory.INVALID_PROTOCOL,
            action=RecoveryAction.LOOPBACK_CORRECTION,
            max_attempts=3,
            message=f"Malformed protocol envelope: {validation_error}",
            guidance="Send structured correction feedback prompt reminding model of strict v1 JSON envelope format.",
        )
