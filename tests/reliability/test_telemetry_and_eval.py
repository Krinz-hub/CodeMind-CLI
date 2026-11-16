"""Hermetic regression tests for Observability, Diagnostics, and Benchmark Evaluation (Phase E).

Covers:
- REL-14: Granular timing segregation (model vs tool time) and token vs character distinction (Workstream L)
- REL-15: System diagnostic bundle generation and environment secret redaction (Workstream L)
- REL-16: 9-category benchmark harness and evaluation records (Workstream M)
"""

from __future__ import annotations

import os
import time
from unittest.mock import patch

from codemind.config import CodeMindConfig
from codemind.telemetry.benchmark import (
    BenchmarkCategory,
    BenchmarkRecord,
    BenchmarkRunner,
    BenchmarkSuiteResult,
)
from codemind.telemetry.metrics import SystemDiagnostics, TaskMetrics
from tests.base import BaseAgentTestCase


class TestTelemetryAndEvaluation(BaseAgentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config = CodeMindConfig.load(
            self.workspace_root,
            overrides={"model": {"provider": "mock"}},
        )

    def test_task_metrics_timing_segregation_and_tokens(self) -> None:
        """Verify model inference time is measured separately from tool execution time."""
        metrics = TaskMetrics(task_id="task-test-01")

        # 1. Record inference (250ms, 120 input chars, 80 output chars, 30 tokens)
        metrics.record_inference(
            duration_ms=250.0,
            in_chars=120,
            out_chars=80,
            in_tokens=30,
            out_tokens=20,
        )

        # 2. Record tool execution (150ms)
        metrics.record_tool_call(duration_ms=150.0)

        # 3. Record repair retry
        metrics.record_repair_retry()

        # Finalize
        metrics.finish(time.time() - 0.5)
        summary = metrics.to_summary_dict()

        # Invariant checks
        self.assertEqual(summary["model_requests"], 1)
        self.assertEqual(summary["tool_calls"], 1)
        self.assertEqual(summary["repair_retries"], 1)
        self.assertEqual(summary["inference_time_ms"], 250.0)
        self.assertEqual(summary["tool_time_ms"], 150.0)

        # Tokens vs characters distinct accounting
        usage = summary["usage"]
        self.assertEqual(usage["measured_input_tokens"], 30)
        self.assertEqual(usage["measured_output_tokens"], 20)
        self.assertEqual(usage["estimated_input_chars"], 120)
        self.assertEqual(usage["estimated_output_chars"], 80)

    def test_system_diagnostics_collection_and_redaction(self) -> None:
        """Verify diagnostic collection redacts sensitive tokens and secret env vars."""
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "sk-secret12345",
            "DATABASE_PASSWORD": "mypassword",
            "SAFE_ENV_VAR": "public_value",
        }):
            diag = SystemDiagnostics.collect(self.config, self.workspace_root)

            self.assertIn("version", diag)
            self.assertIn("python_version", diag)
            self.assertIn("platform", diag)
            self.assertIn("workspace", diag)
            self.assertEqual(diag["model"]["provider"], "mock")

            # Secret redaction validation
            env_redacted = diag["environment_redacted"]
            self.assertEqual(env_redacted.get("OPENAI_API_KEY"), "[REDACTED]")
            self.assertEqual(env_redacted.get("DATABASE_PASSWORD"), "[REDACTED]")
            self.assertEqual(env_redacted.get("SAFE_ENV_VAR"), "public_value")

    def test_benchmark_record_and_suite_evaluation(self) -> None:
        """Verify benchmark suite executes and calculates passed/failed criteria across categories."""
        runner = BenchmarkRunner(self.workspace_root, self.config)

        # Record 1: Passing benchmark in REPO_UNDERSTANDING
        rec1 = runner.create_record(
            benchmark_id="BM-01",
            category=BenchmarkCategory.REPO_UNDERSTANDING,
            prompt="Find main entry point in src/",
            criteria=["identifies_main_file", "explains_architecture"],
            results={"identifies_main_file": True, "explains_architecture": True},
            evidence="Located src/main.py cleanly.",
            duration=1.2,
            model_requests=1,
            tool_calls=2,
        )
        self.assertTrue(rec1.passed)
        self.assertIsNone(rec1.failure_category)

        # Record 2: Failing benchmark in BUG_REPRODUCTION_REPAIR
        rec2 = runner.create_record(
            benchmark_id="BM-02",
            category=BenchmarkCategory.BUG_REPRODUCTION_REPAIR,
            prompt="Fix division by zero in calculator",
            criteria=["reproduces_failure", "applies_fix", "regression_tests_pass"],
            results={"reproduces_failure": True, "applies_fix": True, "regression_tests_pass": False},
            evidence="Unit tests failed after patch.",
            duration=3.5,
            model_requests=2,
            tool_calls=3,
            failure_category="TEST_VERIFICATION_FAILURE",
        )
        self.assertFalse(rec2.passed)
        self.assertEqual(rec2.failure_category, "TEST_VERIFICATION_FAILURE")

        # Suite aggregation
        suite = BenchmarkSuiteResult(records=[rec1, rec2])
        suite.calculate_summary()

        self.assertEqual(suite.total_benchmarks, 2)
        self.assertEqual(suite.passed_count, 1)
        self.assertEqual(suite.failed_count, 1)
        self.assertEqual(suite.pass_rate_percentage, 50.0)
