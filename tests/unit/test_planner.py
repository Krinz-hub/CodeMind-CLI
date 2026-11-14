"""Unit tests for task planning and status updates."""

import unittest

from codemind.models.protocol import PlanAction, TaskPlanItem
from codemind.planning.planner import Planner
from codemind.planning.task import TaskPlan, TaskStatus


class TestPlanner(unittest.TestCase):
    def test_plan_lifecycle(self) -> None:
        plan = TaskPlan()
        t1 = plan.add_or_update("t1", "Explore codebase", TaskStatus.IN_PROGRESS)
        self.assertEqual(t1.status, TaskStatus.IN_PROGRESS)
        self.assertFalse(plan.is_all_completed())

        t1.mark_status(TaskStatus.COMPLETED, evidence="Checked files")
        self.assertTrue(plan.is_all_completed())

    def test_update_from_model_action(self) -> None:
        planner = Planner()
        action = PlanAction(
            plan=[
                TaskPlanItem(id="step-1", title="Inspect repo", status="completed"),
                TaskPlanItem(id="step-2", title="Write tests", status="in_progress"),
            ],
            reason="Step 1 finished",
        )
        planner.update_from_model_action(action)

        self.assertEqual(len(planner.plan.tasks), 2)
        self.assertEqual(planner.plan.tasks[0].status, TaskStatus.COMPLETED)
        self.assertEqual(planner.plan.tasks[1].status, TaskStatus.IN_PROGRESS)
