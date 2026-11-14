"""Task item and task plan state models."""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskItem(BaseModel):
    id: str
    title: str
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    evidence: str = Field(default="", description="Tangible observations or test evidence")
    notes: str = ""
    updated_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def mark_status(self, new_status: TaskStatus, evidence: str = "") -> None:
        self.status = new_status
        if evidence:
            self.evidence = evidence
        self.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()


class TaskPlan(BaseModel):
    """Authoritative task plan maintained by the runtime."""

    tasks: list[TaskItem] = Field(default_factory=list)

    def add_or_update(
        self,
        task_id: str,
        title: str,
        status: TaskStatus = TaskStatus.PENDING,
        notes: str = "",
    ) -> TaskItem:
        for t in self.tasks:
            if t.id == task_id:
                t.title = title
                t.status = status
                if notes:
                    t.notes = notes
                t.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                return t

        item = TaskItem(id=task_id, title=title, status=status, notes=notes)
        self.tasks.append(item)
        return item

    def get_task(self, task_id: str) -> TaskItem | None:
        for t in self.tasks:
            if t.id == task_id:
                return t
        return None

    def get_active_task(self) -> TaskItem | None:
        for t in self.tasks:
            if t.status == TaskStatus.IN_PROGRESS:
                return t
        return None

    def is_all_completed(self) -> bool:
        if not self.tasks:
            return False
        return all(t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED) for t in self.tasks)

    def to_dict_list(self) -> list[dict[str, Any]]:
        return [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status.value,
                "notes": t.notes,
                "evidence": t.evidence,
            }
            for t in self.tasks
        ]

    def format_text(self) -> str:
        if not self.tasks:
            return "No active plan."
        lines: list[str] = []
        for t in self.tasks:
            icon = {
                TaskStatus.COMPLETED: "[✓]",
                TaskStatus.IN_PROGRESS: "[*]",
                TaskStatus.PENDING: "[ ]",
                TaskStatus.FAILED: "[✗]",
                TaskStatus.BLOCKED: "[!]",
                TaskStatus.SKIPPED: "[-]",
            }.get(t.status, "[ ]")
            lines.append(f"{icon} {t.id}: {t.title} ({t.status.value})")
        return "\n".join(lines)
