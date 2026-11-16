"""Data models, error taxonomy, and budget specifications for Workflow Orchestration."""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FailureCategory(str, Enum):
    """Structured failure classification for autonomous recovery."""

    MODEL_RESPONSE_FAILURE = "model_response_failure"
    INVALID_PROTOCOL = "invalid_protocol"
    TOOL_EXECUTION_FAILURE = "tool_execution_failure"
    MISSING_DEPENDENCY = "missing_dependency"
    TEST_FAILURE = "test_failure"
    BUILD_FAILURE = "build_failure"
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    CONTEXT_EXHAUSTION = "context_exhaustion"
    UNCERTAIN_OUTCOME = "uncertain_outcome"


class RecoveryAction(str, Enum):
    """Prescribed recovery action for an identified failure."""

    RETRY_BACKOFF = "retry_backoff"
    LOOPBACK_CORRECTION = "loopback_correction"
    REFRESH_FILE_CONTEXT = "refresh_file_context"
    REPLAN = "replan"
    TEST_DRIVEN_REPAIR = "test_driven_repair"
    BUILD_REPAIR = "build_repair"
    USER_ESCALATION = "user_escalation"
    VERIFY_DISK_OUTCOME = "verify_disk_outcome"
    TERMINATE_GRACEFULLY = "terminate_gracefully"


class RecoveryStrategy(BaseModel):
    """Actionable strategy produced by the FailureClassifier."""

    category: FailureCategory
    action: RecoveryAction
    max_attempts: int = 3
    backoff_seconds: float = 0.5
    message: str = ""
    guidance: str = ""
    retryable: bool = True


class ExecutionBudget(BaseModel):
    """Configurable limits governing autonomous workflow orchestration."""

    max_turns: int = Field(default=40, description="Max total model turns across entire workflow")
    max_tool_calls: int = Field(default=60, description="Max cumulative tool calls")
    max_retries_per_task: int = Field(default=3, description="Max retry attempts per individual task")
    max_execution_time_seconds: int = Field(default=600, description="Total workflow timeout in seconds (10 min)")
    max_concurrent_operations: int = Field(default=2, description="Max safe parallel tasks")
    max_file_modifications: int = Field(default=25, description="Max distinct files mutated per workflow")


class OrchestrationStatus(str, Enum):
    """High-level lifecycle state of the WorkflowOrchestrator."""

    INITIALIZING = "initializing"
    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_FOR_USER = "waiting_for_user"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CompletionStatus(str, Enum):
    """Authoritative honesty rating for workflow completion."""

    COMPLETED_VERIFIED = "completed_verified"
    COMPLETED_UNVERIFIED = "completed_unverified"
    PARTIALLY_COMPLETED = "partially_completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"
