"""Task planner that reconciles model proposals with runtime state."""

from __future__ import annotations

from typing import Any

from codemind.models.protocol import PlanAction, TaskPlanItem
from codemind.planning.task import (
    TaskComplexity,
    TaskItem,
    TaskPlan,
    TaskPriority,
    TaskStatus,
    VerificationCriterion,
)


class Planner:
    """Manages updates, transitions, and verification checks for the structured TaskPlan."""

    def __init__(self, plan: TaskPlan | None = None):
        self.plan = plan or TaskPlan()

    def update_from_model_action(self, action: PlanAction) -> TaskPlan:
        """Update authoritative plan using proposed items from model envelope."""
        for item in action.plan:
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
            parsed_status = status_map.get(item.status.lower(), TaskStatus.PENDING)
            self.plan.add_or_update(
                task_id=item.id,
                title=item.title,
                status=parsed_status,
                notes=item.notes,
            )
        return self.plan

    def record_tool_evidence(self, task_id: str, evidence: str) -> None:
        """Attach observation output to specific task item."""
        task = self.plan.get_task(task_id)
        if task:
            task.evidence = evidence

    def record_file_mutated(self, task_id: str, file_path: str) -> None:
        """Record a file modification under a task."""
        task = self.plan.get_task(task_id)
        if task and file_path not in task.mutated_files:
            task.mutated_files.append(file_path)

    def attach_verification_criterion(
        self,
        task_id: str,
        criterion_type: str,
        target: str,
        expected_value: str = "",
    ) -> bool:
        """Attach a required verification criterion to a task."""
        task = self.plan.get_task(task_id)
        if not task:
            return False
        crit = VerificationCriterion(
            criterion_type=criterion_type,
            target=target,
            expected_value=expected_value,
        )
        task.verification_criteria.append(crit)
        return True

    def satisfy_criterion(
        self,
        task_id: str,
        criterion_type: str,
        target: str,
        actual_value: str = "",
        message: str = "",
    ) -> bool:
        """Mark a specific criterion as satisfied."""
        task = self.plan.get_task(task_id)
        if not task:
            return False
        for c in task.verification_criteria:
            if c.criterion_type == criterion_type and c.target == target:
                c.satisfied = True
                c.actual_value = actual_value
                c.message = message or "Satisfied"
                return True
        return False
