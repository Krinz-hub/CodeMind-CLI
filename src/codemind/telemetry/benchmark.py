"""End-to-End Benchmark Evaluation Harness (Phase E Workstream M).

Executes and audits the 9 standard CodeMind benchmark categories:
1. repo_understanding
2. small_code_change
3. multi_file_feature
4. bug_reproduction_repair
5. test_diagnosis_repair
6. task_interruption_recovery
7. protocol_reliability
8. task_isolation
9. security_permission_enforcement
"""

from __future__ import annotations

import datetime
from enum import Enum
import json
from pathlib import Path
import platform
import time
from typing import Any, Callable

from pydantic import BaseModel, Field

from codemind import __version__
from codemind.config import CodeMindConfig
from codemind.runtime.agent import CodeMindAgent


class BenchmarkCategory(str, Enum):
    REPO_UNDERSTANDING = "repo_understanding"
    SMALL_CODE_CHANGE = "small_code_change"
    MULTI_FILE_FEATURE = "multi_file_feature"
    BUG_REPRODUCTION_REPAIR = "bug_reproduction_repair"
    TEST_DIAGNOSIS_REPAIR = "test_diagnosis_repair"
    TASK_INTERRUPTION_RECOVERY = "task_interruption_recovery"
    PROTOCOL_RELIABILITY = "protocol_reliability"
    TASK_ISOLATION = "task_isolation"
    SECURITY_PERMISSION_ENFORCEMENT = "security_permission_enforcement"


class BenchmarkRecord(BaseModel):
    """Authoritative evaluation record adhering to Section 15.2 requirements."""

    benchmark_id: str
    category: BenchmarkCategory
    prompt: str
    criteria: list[str]
    model_provider: str
    model_name: str
    hardware: dict[str, str] = Field(default_factory=lambda: {
        "platform": platform.platform(),
        "machine": platform.machine(),
    })
    passed: bool = False
    results_per_criterion: dict[str, bool] = Field(default_factory=dict)
    build_test_evidence: str = ""
    model_requests: int = 0
    tool_calls: int = 0
    repair_retries: int = 0
    duration_seconds: float = 0.0
    failure_category: str | None = None
    independent_inspection_status: str = "VERIFIED_HERMETIC"
    timestamp_iso: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class BenchmarkSuiteResult(BaseModel):
    """Aggregated evaluation results across all executed benchmarks."""

    suite_name: str = "CodeMind Reliability Evaluation"
    version: str = __version__
    total_benchmarks: int = 0
    passed_count: int = 0
    failed_count: int = 0
    pass_rate_percentage: float = 0.0
    records: list[BenchmarkRecord] = Field(default_factory=list)

    def calculate_summary(self) -> None:
        self.total_benchmarks = len(self.records)
        self.passed_count = sum(1 for r in self.records if r.passed)
        self.failed_count = self.total_benchmarks - self.passed_count
        self.pass_rate_percentage = round(
            (self.passed_count / self.total_benchmarks * 100.0) if self.total_benchmarks else 0.0,
            2,
        )


class BenchmarkRunner:
    """Executes hermetic benchmark evaluations and audits results."""

    def __init__(self, workspace_root: Path, config: CodeMindConfig):
        self.workspace_root = workspace_root.resolve()
        self.config = config

    def create_record(
        self,
        benchmark_id: str,
        category: BenchmarkCategory,
        prompt: str,
        criteria: list[str],
        results: dict[str, bool],
        evidence: str,
        duration: float,
        model_requests: int = 1,
        tool_calls: int = 0,
        repair_retries: int = 0,
        failure_category: str | None = None,
    ) -> BenchmarkRecord:
        """Create and populate a verified benchmark record."""
        passed = all(results.get(c, False) for c in criteria)
        return BenchmarkRecord(
            benchmark_id=benchmark_id,
            category=category,
            prompt=prompt,
            criteria=criteria,
            model_provider=self.config.model.provider.value,
            model_name=self.config.model.model_name,
            passed=passed,
            results_per_criterion=results,
            build_test_evidence=evidence,
            model_requests=model_requests,
            tool_calls=tool_calls,
            repair_retries=repair_retries,
            duration_seconds=round(duration, 3),
            failure_category=failure_category if not passed else None,
        )
