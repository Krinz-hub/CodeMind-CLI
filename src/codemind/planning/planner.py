"""Task planner that reconciles model proposals with runtime state."""

from __future__ import annotations

from codemind.models.protocol import PlanAction, TaskPlanItem
from codemind.planning.task import TaskItem, TaskPlan, TaskStatus


class Planner:
    """Manages updates and transitions to the structured TaskPlan."""

    def __init__(self, plan: TaskPlan | None = None):
        self.plan = plan or TaskPlan()

    def update_from_model_action(self, action: PlanAction) -> TaskPlan:
        """Update authoritative plan using proposed items from model envelope."""
        for item in action.plan:
            # Map string status to TaskStatus enum
            status_map = {
                "pending": TaskStatus.PENDING,
                "in_progress": TaskStatus.IN_PROGRESS,
                "completed": TaskStatus.COMPLETED,
                "failed": TaskStatus.FAILED,
                "blocked": TaskStatus.BLOCKED,
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
