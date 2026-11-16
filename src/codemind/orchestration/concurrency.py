"""Concurrency control and conflict detection for independent task execution."""

from __future__ import annotations

import asyncio
from typing import Any

from codemind.planning.task import TaskItem, TaskPlan


class ConcurrencyController:
    """Manages file locks, conflict detection, and safe concurrency bounds."""

    def __init__(self, max_concurrent: int = 2):
        self.max_concurrent = max_concurrent
        self._active_file_locks: set[str] = set()
        self._lock = asyncio.Lock()

    async def acquire_file_locks(self, files: list[str]) -> bool:
        """Attempt to acquire exclusive file locks for a mutating task."""
        async with self._lock:
            for f in files:
                clean_f = f.strip().lower()
                if clean_f in self._active_file_locks:
                    return False
            for f in files:
                self._active_file_locks.add(f.strip().lower())
            return True

    async def release_file_locks(self, files: list[str]) -> None:
        """Release previously acquired file locks."""
        async with self._lock:
            for f in files:
                self._active_file_locks.discard(f.strip().lower())

    def check_task_conflicts(
        self,
        candidate_tasks: list[TaskItem],
        plan: TaskPlan,
    ) -> list[TaskItem]:
        """Filter a list of READY tasks down to a subset that can run concurrently without file conflicts."""
        if len(candidate_tasks) <= 1:
            return candidate_tasks

        selected: list[TaskItem] = []
        occupied_files: set[str] = set(self._active_file_locks)

        for task in candidate_tasks:
            task_files = set(task.relevant_files + task.mutated_files + task.expected_outputs)
            clean_files = {f.strip().lower() for f in task_files}

            # Check if task conflicts with currently locked files or already selected tasks
            if clean_files.intersection(occupied_files):
                continue  # Conflicted, cannot run concurrently

            selected.append(task)
            occupied_files.update(clean_files)

            if len(selected) >= self.max_concurrent:
                break

        return selected
