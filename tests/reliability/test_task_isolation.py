"""Reliability regression tests for task isolation and file change ledger (REL-04, REL-05)."""

import asyncio
import unittest
from pathlib import Path

from codemind.cli.ui import TerminalUI
from codemind.config import CodeMindConfig, ModelProvider, PermissionMode
from codemind.models.mock import MockModelAdapter
from codemind.orchestration.checkpoint import CheckpointManager, WorkflowCheckpoint
from codemind.runtime.agent import CodeMindAgent
from tests.base import BaseAgentTestCase


class TestTaskIsolation(BaseAgentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config.security.permission_mode = PermissionMode.TRUSTED

    def test_rel_04_consecutive_task_file_purity(self) -> None:
        """REL-04: When running two consecutive tasks in the same agent session,

        Task B must ONLY report files created during Task B, not files from Task A.
        """
        ui = TerminalUI(plain_mode=True)
        agent = CodeMindAgent(config=self.config, ui=ui)
        asyncio.run(agent.initialize())

        # Task 1: Create Task A file
        task_1_script = [
            '{"protocol_version": "1", "type": "tool_call", "tool": "create_file", "arguments": {"path": "documents/task_a/index.html", "content": "<h1>Task A</h1>"}, "reason": "Create Task A"}',
            '{"protocol_version": "1", "type": "final", "content": "Task A done", "summary": ["Created task A"]}',
        ]
        agent.model = MockModelAdapter(responses=task_1_script)
        state_1 = asyncio.run(agent.run_task("Build Task A deliverable"))
        self.assertTrue(any("documents/task_a/index.html" in f for f in state_1.files_created))

        # Task 2: Create Task B file in the same session
        task_2_script = [
            '{"protocol_version": "1", "type": "tool_call", "tool": "create_file", "arguments": {"path": "documents/task_b/index.html", "content": "<h1>Task B</h1>"}, "reason": "Create Task B"}',
            '{"protocol_version": "1", "type": "final", "content": "Task B done", "summary": ["Created task B"]}',
        ]
        agent.model = MockModelAdapter(responses=task_2_script)
        state_2 = asyncio.run(agent.run_task("Build Task B deliverable"))

        # Invariant: Task 2 must NOT have Task 1's files in files_created!
        self.assertTrue(any("documents/task_b/index.html" in f for f in state_2.files_created))
        self.assertFalse(
            any("documents/task_a/index.html" in f for f in state_2.files_created),
            "Invariant violation: Task A files leaked into Task B's change ledger!",
        )

    def test_rel_05_unrelated_task_does_not_inherit_stale_checkpoint_files(self) -> None:
        """REL-05: An incomplete checkpoint from a prior task must not contaminate

        a new independent task with stale file records.
        """
        ckpt_mgr = CheckpointManager(self.workspace_root)
        stale_ckpt = WorkflowCheckpoint(
            session_id="cm-prior-session",
            workspace_root=str(self.workspace_root),
            instruction="Build Instagram clone",
            current_task_id="task-stale-999",
            tasks=[{"id": "t1", "title": "Old task", "status": "in_progress"}],
            files_created=["documents/insta_gram/index.html", "documents/flappy_bird/index.html"],
            files_modified=[],
            is_completed=False,
        )
        ckpt_mgr.save_checkpoint_atomic(stale_ckpt)

        ui = TerminalUI(plain_mode=True)
        agent = CodeMindAgent(config=self.config, ui=ui)
        asyncio.run(agent.initialize())

        # Start a brand new task (not a resumption of task-stale-999)
        new_task_script = [
            '{"protocol_version": "1", "type": "tool_call", "tool": "create_file", "arguments": {"path": "documents/portfolio/index.html", "content": "<h1>Portfolio</h1>"}, "reason": "Create Portfolio"}',
            '{"protocol_version": "1", "type": "final", "content": "Portfolio created", "summary": ["Created portfolio"]}',
        ]
        agent.model = MockModelAdapter(responses=new_task_script)
        new_state = asyncio.run(agent.run_task("Build React portfolio"))

        # Invariant: Stale files from insta_gram or flappy_bird must NOT be present
        self.assertTrue(any("documents/portfolio/index.html" in f for f in new_state.files_created))
        self.assertFalse(any("documents/insta_gram/index.html" in f for f in new_state.files_created))
        self.assertFalse(any("documents/flappy_bird/index.html" in f for f in new_state.files_created))


if __name__ == "__main__":
    unittest.main()
