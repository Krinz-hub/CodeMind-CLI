"""Core task management service."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Task:
    id: str
    title: str
    priority: TaskPriority = TaskPriority.MEDIUM
    tags: list[str] = field(default_factory=list)
    completed: bool = False
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )


class TaskManager:
    """Manages an in-memory collection of tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def create_task(
        self,
        task_id: str,
        title: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        tags: list[str] | None = None,
    ) -> Task:
        if task_id in self._tasks:
            raise ValueError(f"Task with ID '{task_id}' already exists")
        task = Task(id=task_id, title=title, priority=priority, tags=tags or [])
        self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def complete_task(self, task_id: str) -> Task:
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found")
        task.completed = True
        return task

    def list_tasks(self, include_completed: bool = True) -> list[Task]:
        tasks = list(self._tasks.values())
        if not include_completed:
            return [t for t in tasks if not t.completed]
        return tasks

    def filter_by_tag(self, tag: str) -> list[Task]:
        return [t for t in self._tasks.values() if tag in t.tags]
