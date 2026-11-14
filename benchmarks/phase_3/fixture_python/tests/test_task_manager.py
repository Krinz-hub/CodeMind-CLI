"""Unit tests for TaskManager."""

import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import unittest
from task_manager import TaskManager, TaskPriority


class TestTaskManager(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = TaskManager()

    def test_create_and_get_task(self) -> None:
        t = self.manager.create_task("t-1", "Implement auth", TaskPriority.HIGH, ["security", "backend"])
        self.assertEqual(t.id, "t-1")
        self.assertEqual(t.priority, TaskPriority.HIGH)
        self.assertFalse(t.completed)

        retrieved = self.manager.get_task("t-1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.title, "Implement auth")

    def test_complete_task(self) -> None:
        self.manager.create_task("t-2", "Write docs")
        completed = self.manager.complete_task("t-2")
        self.assertTrue(completed.completed)

    def test_filter_by_tag(self) -> None:
        self.manager.create_task("t-3", "Fix CSS", tags=["ui"])
        self.manager.create_task("t-4", "Add dark mode", tags=["ui", "frontend"])
        self.manager.create_task("t-5", "Deploy DB", tags=["infra"])

        ui_tasks = self.manager.filter_by_tag("ui")
        self.assertEqual(len(ui_tasks), 2)


if __name__ == "__main__":
    unittest.main()
