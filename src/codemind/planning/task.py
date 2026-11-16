"""Task item and task plan state models with DAG orchestration support."""

from __future__ import annotations

import datetime
from collections import defaultdict, deque
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskComplexity(str, Enum):
    TRIVIAL = "trivial"
    MODERATE = "moderate"
    COMPLEX = "complex"


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    IN_PROGRESS = "in_progress"  # Backward-compatibility alias for RUNNING
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    BLOCKED = "blocked"
    FAILED = "failed"
    PAUSED = "paused"
    RETRYING = "retrying"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"  # Backward-compatibility alias


class VerificationCriterion(BaseModel):
    """Specification for verifiable evidence required before task completion."""

    criterion_type: str = Field(
        ...,
        description="Type of verification: file_exists, test_passes, command_exits_zero, diff_contains, custom",
    )
    target: str = Field(..., description="Target file path, test pattern, or command string")
    expected_value: str = ""
    actual_value: str = ""
    satisfied: bool = False
    message: str = ""


class TaskItem(BaseModel):
    """Execution unit within a hierarchical DAG task plan."""

    id: str
    title: str
    parent_id: str | None = None
    description: str = ""
    priority: TaskPriority = TaskPriority.NORMAL
    complexity: TaskComplexity = TaskComplexity.MODERATE
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    verification_criteria: list[VerificationCriterion] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    mutated_files: list[str] = Field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    evidence: str = Field(default="", description="Tangible observations or test evidence")
    error_message: str = ""
    notes: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def mark_status(self, new_status: TaskStatus, evidence: str = "") -> None:
        """Update task status with timestamp and optional evidence."""
        self.status = new_status
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if new_status in (TaskStatus.RUNNING, TaskStatus.IN_PROGRESS) and not self.started_at:
            self.started_at = now_iso
        elif new_status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED):
            self.completed_at = now_iso
        if evidence:
            self.evidence = evidence
        self.updated_at = now_iso

    def check_verification_satisfied(self) -> tuple[bool, list[str]]:
        """Verify if all defined verification criteria have been satisfied."""
        if not self.verification_criteria:
            return True, []
        unsatisfied = [
            f"{c.criterion_type}: {c.target} ({c.message or 'unsatisfied'})"
            for c in self.verification_criteria
            if not c.satisfied
        ]
        return len(unsatisfied) == 0, unsatisfied


class TaskPlan(BaseModel):
    """Authoritative task plan with hierarchical DAG scheduling and cycle detection."""

    tasks: list[TaskItem] = Field(default_factory=list)

    def add_or_update(
        self,
        task_id: str,
        title: str,
        status: TaskStatus = TaskStatus.PENDING,
        notes: str = "",
        parent_id: str | None = None,
        dependencies: list[str] | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        complexity: TaskComplexity = TaskComplexity.MODERATE,
        expected_outputs: list[str] | None = None,
        verification_criteria: list[VerificationCriterion] | None = None,
        relevant_files: list[str] | None = None,
        evidence: str = "",
    ) -> TaskItem:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for t in self.tasks:
            if t.id == task_id:
                t.title = title
                t.status = status
                if notes:
                    t.notes = notes
                if parent_id is not None:
                    t.parent_id = parent_id
                if dependencies is not None:
                    t.dependencies = list(dependencies)
                if expected_outputs is not None:
                    t.expected_outputs = list(expected_outputs)
                if verification_criteria is not None:
                    t.verification_criteria = list(verification_criteria)
                if relevant_files is not None:
                    t.relevant_files = list(relevant_files)
                if evidence:
                    t.evidence = evidence
                t.priority = priority
                t.complexity = complexity
                t.updated_at = now_iso
                return t

        item = TaskItem(
            id=task_id,
            title=title,
            status=status,
            notes=notes,
            parent_id=parent_id,
            dependencies=list(dependencies or []),
            priority=priority,
            complexity=complexity,
            expected_outputs=list(expected_outputs or []),
            verification_criteria=list(verification_criteria or []),
            relevant_files=list(relevant_files or []),
            evidence=evidence,
        )
        self.tasks.append(item)
        return item

    def get_task(self, task_id: str) -> TaskItem | None:
        for t in self.tasks:
            if t.id == task_id:
                return t
        return None

    def get_active_task(self) -> TaskItem | None:
        for t in self.tasks:
            if t.status in (TaskStatus.IN_PROGRESS, TaskStatus.RUNNING, TaskStatus.VERIFYING):
                return t
        return None

    def is_all_completed(self) -> bool:
        if not self.tasks:
            return False
        return all(t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED) for t in self.tasks)

    def has_failures(self) -> bool:
        return any(t.status in (TaskStatus.FAILED, TaskStatus.CANCELLED) for t in self.tasks)

    def get_ready_tasks(self) -> list[TaskItem]:
        """Return tasks whose dependencies are completely satisfied."""
        completed_ids = {
            t.id for t in self.tasks if t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
        }
        ready: list[TaskItem] = []
        for t in self.tasks:
            if t.status in (TaskStatus.PENDING, TaskStatus.READY):
                # All dependencies must be satisfied
                deps_met = all(dep in completed_ids for dep in t.dependencies)
                if deps_met:
                    ready.append(t)
        # Sort ready tasks by priority then complexity
        priority_rank = {
            TaskPriority.CRITICAL: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.NORMAL: 2,
            TaskPriority.LOW: 3,
        }
        ready.sort(key=lambda item: priority_rank.get(item.priority, 2))
        return ready

    def detect_cycles(self) -> list[list[str]]:
        """Detect any cycles in the dependency graph using DFS."""
        adj: dict[str, list[str]] = defaultdict(list)
        all_ids = {t.id for t in self.tasks}
        for t in self.tasks:
            for dep in t.dependencies:
                if dep in all_ids:
                    adj[dep].append(t.id)

        visited: dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited
        cycles: list[list[str]] = []

        def dfs(node: str, path: list[str]) -> None:
            visited[node] = 1
            path.append(node)
            for nxt in adj[node]:
                if visited.get(nxt, 0) == 1:
                    cycle_start = path.index(nxt)
                    cycles.append(list(path[cycle_start:]))
                elif visited.get(nxt, 0) == 0:
                    dfs(nxt, path)
            path.pop()
            visited[node] = 2

        for tid in all_ids:
            if visited.get(tid, 0) == 0:
                dfs(tid, [])

        return cycles

    def get_topological_order(self) -> list[TaskItem]:
        """Compute topological ordering of tasks respecting dependencies."""
        if self.detect_cycles():
            return list(self.tasks)  # Fallback to linear if cycles exist

        in_degree: dict[str, int] = {t.id: 0 for t in self.tasks}
        adj: dict[str, list[str]] = defaultdict(list)
        task_map = {t.id: t for t in self.tasks}

        for t in self.tasks:
            for dep in t.dependencies:
                if dep in in_degree:
                    adj[dep].append(t.id)
                    in_degree[t.id] += 1

        queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
        ordered: list[TaskItem] = []

        while queue:
            curr_id = queue.popleft()
            if curr_id in task_map:
                ordered.append(task_map[curr_id])
            for nxt in adj[curr_id]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        return ordered if len(ordered) == len(self.tasks) else list(self.tasks)

    def can_parallelize(self, task_a_id: str, task_b_id: str) -> tuple[bool, str]:
        """Determine whether two tasks can safely execute in parallel without conflict."""
        a = self.get_task(task_a_id)
        b = self.get_task(task_b_id)
        if not a or not b:
            return False, "Task not found"

        # Check direct dependencies
        if task_b_id in a.dependencies or task_a_id in b.dependencies:
            return False, f"Direct dependency exists between '{task_a_id}' and '{task_b_id}'"

        # Check mutated file conflicts
        a_mutated = set(a.mutated_files or a.expected_outputs)
        b_mutated = set(b.mutated_files or b.expected_outputs)
        overlap_mutated = a_mutated.intersection(b_mutated)
        if overlap_mutated:
            return False, f"Shared mutable files: {', '.join(overlap_mutated)}"

        # Check read-write conflict (A mutates file that B reads, or vice versa)
        a_relevant = set(a.relevant_files)
        b_relevant = set(b.relevant_files)
        if a_mutated.intersection(b_relevant):
            return False, f"Task '{task_a_id}' mutates files read by '{task_b_id}'"
        if b_mutated.intersection(a_relevant):
            return False, f"Task '{task_b_id}' mutates files read by '{task_a_id}'"

        return True, "Safe for parallel execution"

    def mark_task_completed(self, task_id: str, evidence: str = "") -> tuple[bool, str]:
        """Mark task as completed only if all verification criteria are satisfied."""
        task = self.get_task(task_id)
        if not task:
            return False, f"Task '{task_id}' not found."

        satisfied, unsatisfied_reasons = task.check_verification_satisfied()
        if not satisfied:
            task.mark_status(TaskStatus.FAILED, evidence=f"Verification failed: {'; '.join(unsatisfied_reasons)}")
            return False, f"Cannot complete '{task_id}': Unsatisfied verification criteria: {'; '.join(unsatisfied_reasons)}"

        task.mark_status(TaskStatus.COMPLETED, evidence=evidence)
        return True, "Task verified and completed successfully."

    def to_dict_list(self) -> list[dict[str, Any]]:
        return [
            {
                "id": t.id,
                "parent_id": t.parent_id,
                "title": t.title,
                "priority": t.priority.value,
                "complexity": t.complexity.value,
                "status": t.status.value,
                "dependencies": t.dependencies,
                "expected_outputs": t.expected_outputs,
                "relevant_files": t.relevant_files,
                "notes": t.notes,
                "evidence": t.evidence,
                "retry_count": t.retry_count,
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
                TaskStatus.RUNNING: "[*]",
                TaskStatus.IN_PROGRESS: "[*]",
                TaskStatus.VERIFYING: "[?]",
                TaskStatus.READY: "[·]",
                TaskStatus.PENDING: "[ ]",
                TaskStatus.WAITING_FOR_APPROVAL: "[!]",
                TaskStatus.RETRYING: "[⟳]",
                TaskStatus.FAILED: "[✗]",
                TaskStatus.BLOCKED: "[⊘]",
                TaskStatus.CANCELLED: "[-]",
                TaskStatus.SKIPPED: "[-]",
            }.get(t.status, "[ ]")
            dep_str = f" (depends on: {', '.join(t.dependencies)})" if t.dependencies else ""
            lines.append(f"{icon} {t.id}: {t.title} [{t.status.value.upper()}]{dep_str}")
        return "\n".join(lines)
