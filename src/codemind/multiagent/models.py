"""Data models, role definitions, and message schemas for Multi-Agent Collaboration."""

from __future__ import annotations

import datetime
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    """Specialized roles for multi-agent software engineering."""

    COORDINATOR = "coordinator"
    RESEARCH = "research"
    CODING = "coding"
    DEBUGGING = "debugging"
    TESTING = "testing"


class WorkerStatus(str, Enum):
    """Lifecycle states of a worker agent managed by the sidecar."""

    IDLE = "idle"
    ASSIGNED = "assigned"
    RUNNING = "running"
    WAITING_INFERENCE = "waiting_inference"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


class MessageType(str, Enum):
    """Inter-Agent Communication Protocol (IACP v1) message types."""

    TASK_ASSIGNMENT = "task_assignment"
    TASK_ACCEPTED = "task_accepted"
    PROGRESS_UPDATE = "progress_update"
    FINDINGS = "findings"
    CHANGE_PROPOSAL = "change_proposal"
    TOOL_REQUEST = "tool_request"
    TOOL_RESULT = "tool_result"
    BLOCKED = "blocked"
    FAILURE = "failure"
    TASK_COMPLETED = "task_completed"
    REVIEW_REQUEST = "review_request"


class InterAgentMessage(BaseModel):
    """Versioned structured message payload for inter-agent communication."""

    message_id: str = Field(default_factory=lambda: f"msg-{uuid.uuid4().hex[:8]}")
    task_id: str
    sender_agent: str
    recipient: str
    timestamp: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    message_type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class WorkerConfig(BaseModel):
    """Configuration bundle defining a worker's role, sandbox, and budget."""

    worker_id: str
    role: AgentRole
    workspace_path: str
    max_turns: int = 15
    context_limit_tokens: int = 16384
    memory_context: str = ""
    assigned_skills: list[str] = Field(default_factory=list)
    read_only: bool = False


class ChangeProposal(BaseModel):
    """Structured proposal containing file modifications produced by a worker."""

    proposal_id: str = Field(default_factory=lambda: f"prop-{uuid.uuid4().hex[:8]}")
    worker_id: str
    task_id: str
    modified_files: list[str] = Field(default_factory=list)
    created_files: list[str] = Field(default_factory=list)
    diffs: dict[str, str] = Field(default_factory=dict, description="File path to unified diff")
    summary: str = ""
    timestamp: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )


class MultiAgentConfig(BaseModel):
    """Global configuration settings for the multi-agent runtime."""

    max_workers: int = Field(default=4, description="Maximum concurrent worker agents")
    max_concurrent_inferences: int = Field(default=1, description="Bounded LLM generation concurrency")
    inference_timeout_seconds: int = Field(default=180, description="Timeout for single inference turns")
    sequential_mode: bool = Field(default=False, description="Force sequential subtask execution")
    worker_workspace_dir: str = Field(default=".codemind/workspaces", description="Base directory for worker sandboxes")
