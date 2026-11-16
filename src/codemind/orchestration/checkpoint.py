"""Atomic checkpointing and recovery store for long-running workflows."""

from __future__ import annotations

import datetime
import json
import os
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codemind.planning.task import TaskItem, TaskPlan, TaskStatus
from codemind.security.redaction import redact_secrets


class WorkflowCheckpoint(BaseModel):
    """Full snapshot of orchestrator execution state at a point in time."""

    checkpoint_id: str = Field(
        default_factory=lambda: f"ckpt-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    )
    session_id: str
    workspace_root: str
    timestamp: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    instruction: str
    current_task_id: str | None = None
    execution_position: int = 0
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    completed_task_ids: list[str] = Field(default_factory=list)
    pending_task_ids: list[str] = Field(default_factory=list)
    failed_task_ids: list[str] = Field(default_factory=list)
    tool_observations: list[dict[str, Any]] = Field(default_factory=list)
    model_decisions: list[dict[str, Any]] = Field(default_factory=list)
    permission_state: dict[str, Any] = Field(default_factory=dict)
    verification_evidence: dict[str, Any] = Field(default_factory=dict)
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    total_turns: int = 0
    total_tool_calls: int = 0
    is_completed: bool = False


class CheckpointManager:
    """Manages atomic writing and recovery of WorkflowCheckpoints under .codemind/checkpoints/."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.checkpoints_dir = self.workspace_root / ".codemind" / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint_atomic(self, checkpoint: WorkflowCheckpoint) -> Path:
        """Atomically persist checkpoint using fsync and atomic rename."""
        checkpoint.timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        final_path = self.checkpoints_dir / f"{checkpoint.session_id}_{checkpoint.checkpoint_id}.json"
        temp_path = self.checkpoints_dir / f"{checkpoint.session_id}_{checkpoint.checkpoint_id}.tmp.{os.getpid()}"

        raw_json = checkpoint.model_dump_json(indent=2)
        clean_json = redact_secrets(raw_json)

        # Write to temporary file, sync to disk, then atomically replace
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(clean_json)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, final_path)

        # Also write a symlink/pointer to latest checkpoint for this session
        latest_path = self.checkpoints_dir / f"{checkpoint.session_id}_latest.json"
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(clean_json)

        return final_path

    def load_latest_checkpoint(self, session_id: str) -> WorkflowCheckpoint | None:
        """Load the most recent safe checkpoint for a session."""
        latest_file = self.checkpoints_dir / f"{session_id}_latest.json"
        if latest_file.is_file():
            try:
                with open(latest_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return WorkflowCheckpoint.model_validate(data)
            except Exception:
                pass

        # Fallback: scan all checkpoints matching session_id sorted by timestamp
        matching = sorted(self.checkpoints_dir.glob(f"{session_id}_ckpt-*.json"), reverse=True)
        if matching:
            try:
                with open(matching[0], "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return WorkflowCheckpoint.model_validate(data)
            except Exception:
                return None
        return None

    def list_checkpoints(self, session_id: str | None = None) -> list[dict[str, Any]]:
        """List available checkpoints with metadata."""
        pattern = f"{session_id}_ckpt-*.json" if session_id else "*_ckpt-*.json"
        checkpoints: list[dict[str, Any]] = []
        for file in sorted(self.checkpoints_dir.glob(pattern), reverse=True):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    checkpoints.append({
                        "checkpoint_id": data.get("checkpoint_id", file.stem),
                        "session_id": data.get("session_id", ""),
                        "timestamp": data.get("timestamp", ""),
                        "current_task": data.get("current_task_id", ""),
                        "completed_tasks": len(data.get("completed_task_ids", [])),
                        "pending_tasks": len(data.get("pending_task_ids", [])),
                        "is_completed": data.get("is_completed", False),
                    })
            except Exception:
                continue
        return checkpoints

    def reconstruct_plan_from_checkpoint(self, checkpoint: WorkflowCheckpoint) -> TaskPlan:
        """Reconstruct an authoritative TaskPlan from checkpoint records."""
        plan = TaskPlan()
        for t_dict in checkpoint.tasks:
            status_str = t_dict.get("status", "pending")
            status_map = {
                "pending": TaskStatus.PENDING,
                "ready": TaskStatus.READY,
                "running": TaskStatus.RUNNING,
                "in_progress": TaskStatus.IN_PROGRESS,
                "waiting_for_approval": TaskStatus.WAITING_FOR_APPROVAL,
                "blocked": TaskStatus.BLOCKED,
                "failed": TaskStatus.FAILED,
                "retrying": TaskStatus.RETRYING,
                "verifying": TaskStatus.VERIFYING,
                "completed": TaskStatus.COMPLETED,
                "cancelled": TaskStatus.CANCELLED,
                "skipped": TaskStatus.SKIPPED,
            }
            status = status_map.get(status_str.lower(), TaskStatus.PENDING)
            item = plan.add_or_update(
                task_id=t_dict["id"],
                title=t_dict.get("title", ""),
                status=status,
                notes=t_dict.get("notes", ""),
                parent_id=t_dict.get("parent_id"),
                dependencies=t_dict.get("dependencies", []),
                expected_outputs=t_dict.get("expected_outputs", []),
                relevant_files=t_dict.get("relevant_files", []),
            )
            item.evidence = t_dict.get("evidence", "")
            item.retry_count = t_dict.get("retry_count", 0)
        return plan
