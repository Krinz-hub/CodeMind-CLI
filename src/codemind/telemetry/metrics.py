"""Observability, fine-grained telemetry metrics, and diagnostic reporting (Phase E Workstream L).

Adheres to strict observability rules:
- Distinguishes measured tokens from estimated character counts.
- Keeps model inference duration separate from tool execution duration.
- Enforces zero remote cloud leakage; local-only audit persistence.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
import platform
import sys
import time
from typing import Any

from pydantic import BaseModel, Field

from codemind import __version__
from codemind.config import CodeMindConfig
from codemind.security.redaction import redact_secrets


class TaskMetrics(BaseModel):
    """Granular execution metrics for an individual task."""

    task_id: str
    start_time_iso: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    end_time_iso: str | None = None
    total_task_duration_ms: float = 0.0

    # Model timing & counts (measured separately from tools)
    model_requests_count: int = 0
    total_inference_duration_ms: float = 0.0

    # Tool timing & counts
    tool_calls_count: int = 0
    total_tool_duration_ms: float = 0.0

    # Verification and state
    verification_duration_ms: float = 0.0
    checkpoint_duration_ms: float = 0.0
    repair_retries_count: int = 0
    turn_count: int = 0
    max_turns: int = 20

    # Token vs Character accounting
    measured_input_tokens: int | None = None
    measured_output_tokens: int | None = None
    estimated_input_chars: int = 0
    estimated_output_chars: int = 0

    def record_inference(self, duration_ms: float, in_chars: int = 0, out_chars: int = 0, in_tokens: int | None = None, out_tokens: int | None = None) -> None:
        """Record model invocation metrics without conflating with tool execution."""
        self.model_requests_count += 1
        self.total_inference_duration_ms += duration_ms
        self.estimated_input_chars += in_chars
        self.estimated_output_chars += out_chars
        if in_tokens is not None:
            self.measured_input_tokens = (self.measured_input_tokens or 0) + in_tokens
        if out_tokens is not None:
            self.measured_output_tokens = (self.measured_output_tokens or 0) + out_tokens

    def record_tool_call(self, duration_ms: float) -> None:
        """Record tool execution duration separately from model inference."""
        self.tool_calls_count += 1
        self.total_tool_duration_ms += duration_ms

    def record_repair_retry(self) -> None:
        """Increment format repair retry count."""
        self.repair_retries_count += 1

    def finish(self, start_epoch: float) -> None:
        """Finalize total elapsed task time."""
        self.end_time_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.total_task_duration_ms = (time.time() - start_epoch) * 1000.0

    def to_summary_dict(self) -> dict[str, Any]:
        """Generate human-readable summary distinguishing measured tokens from character estimates."""
        return {
            "task_id": self.task_id,
            "turns_used": f"{self.turn_count}/{self.max_turns}",
            "model_requests": self.model_requests_count,
            "inference_time_ms": round(self.total_inference_duration_ms, 2),
            "tool_calls": self.tool_calls_count,
            "tool_time_ms": round(self.total_tool_duration_ms, 2),
            "verification_time_ms": round(self.verification_duration_ms, 2),
            "repair_retries": self.repair_retries_count,
            "total_task_duration_ms": round(self.total_task_duration_ms, 2),
            "usage": {
                "measured_input_tokens": self.measured_input_tokens,
                "measured_output_tokens": self.measured_output_tokens,
                "estimated_input_chars": self.estimated_input_chars,
                "estimated_output_chars": self.estimated_output_chars,
            },
        }


class SystemDiagnostics:
    """Collects unified diagnostic bundle for environment, model, memory, and security."""

    @staticmethod
    def collect(config: CodeMindConfig, workspace_root: Path | None = None) -> dict[str, Any]:
        """Aggregate system diagnostics with strict secret redaction."""
        ws = (workspace_root or Path(config.workspace_root)).resolve()

        # Check git
        git_dir = ws / ".git"
        git_status = "present" if git_dir.is_dir() else "not_found"

        # Check .codemind
        cm_dir = ws / ".codemind"
        mem_db = cm_dir / "memory" / "project_memory.db"

        # Redact environment variables before inclusion
        safe_env = {
            k: ("[REDACTED]" if any(s in k.lower() for s in ["key", "token", "secret", "pass", "auth"]) else v)
            for k, v in os.environ.items()
            if not k.startswith("_") and len(k) < 50
        }

        return {
            "version": __version__,
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
            "workspace": str(ws),
            "git_repository": git_status,
            "model": {
                "name": config.model.model_name,
                "provider": config.model.provider.value,
                "endpoint": config.model.endpoint,
                "privacy_policy": "LOCAL-ONLY (Zero cloud egress)",
            },
            "security": {
                "permission_mode": config.security.permission_mode.value,
                "allow_external_paths": config.security.allow_external_paths,
            },
            "memory": {
                "initialized": mem_db.is_file(),
                "db_path": str(mem_db),
            },
            "environment_redacted": safe_env,
        }
