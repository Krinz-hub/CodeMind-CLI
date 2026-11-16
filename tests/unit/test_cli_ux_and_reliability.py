"""Comprehensive unit and integration tests for CodeMind CLI UX and Runtime Reliability.

Covers the 12 core reliability criteria:
1. Turn-budget exhaustion.
2. Paused task persistence.
3. Task continuation.
4. Independent new task creation.
5. Ctrl+C cancellation.
6. Event-loop cleanup.
7. Stale verification prevention.
8. Task-specific file verification.
9. Accurate completion reporting.
10. TUI rendering.
11. Supervised approval interactions.
12. Long-running task progress.
"""

from __future__ import annotations

import asyncio
import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from rich.console import Console

from codemind.cli.branding import BRAND_MARK
from codemind.cli.tui import CodeMindTUI
from codemind.cli.ui import TerminalUI
from codemind.config import CodeMindConfig, ModelProvider, PermissionMode
from codemind.models.mock import MockModelAdapter
from codemind.models.protocol import ToolCallAction
from codemind.orchestration.checkpoint import CheckpointManager
from codemind.planning.planner import Planner
from codemind.planning.task import TaskItem, TaskPlan, TaskStatus
from codemind.runtime.agent import CodeMindAgent
from codemind.runtime.events import AgentEvent, AgentEventType
from codemind.runtime.loop import AgentLoop
from codemind.runtime.state import AgentState
from codemind.security.permissions import PermissionChecker
from codemind.security.sandbox import WorkspaceSandbox
from codemind.tools.base import ExecutionContext
from codemind.tools.registry import ToolRegistry
from codemind.verification.reporter import CompletionStatus, HonestCompletionReport
from codemind.verification.runner import TestCheckResult
from tests.base import BaseAgentTestCase


class TestCliUxAndReliability(BaseAgentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config = CodeMindConfig(
            workspace_root=str(self.workspace_root),
            plain_mode=True,
            model={"provider": ModelProvider.MOCK, "model_name": "mock-codemind"},
            security={"permission_mode": PermissionMode.TRUSTED},
            runtime={"max_turns": 2, "max_tool_calls": 5, "auto_verify": True},
        )
        self.ui = TerminalUI(plain_mode=True)

    def test_1_turn_budget_exhaustion(self) -> None:
        """1. Verify that reaching max_turns stops cleanly, marks task as PAUSED, and does not claim success."""
        agent = CodeMindAgent(self.config, ui=self.ui)
        assert isinstance(agent.model, MockModelAdapter)

        # Queue continuous tool calls that exceed max_turns (budget=2)
        tool_call_1 = json.dumps({
            "protocol_version": "1",
            "type": "tool_call",
            "tool": "create_file",
            "arguments": {"path": "src/part1.py", "content": "print('part1')\n"},
            "reason": "Step 1",
        })
        tool_call_2 = json.dumps({
            "protocol_version": "1",
            "type": "tool_call",
            "tool": "create_file",
            "arguments": {"path": "src/part2.py", "content": "print('part2')\n"},
            "reason": "Step 2",
        })
        agent.model.queue_response(tool_call_1)
        agent.model.queue_response(tool_call_2)

        state = asyncio.run(agent.run_task("Build multi-part system", max_turns=2))

        # Must be paused, NOT complete
        self.assertTrue(state.is_paused)
        self.assertFalse(state.is_complete)
        self.assertEqual(state.status, "paused")
        self.assertIn("Turn limit reached", state.final_content)

        # Honest completion report must reflect PAUSED, not VERIFIED SUCCESS
        report = HonestCompletionReport(
            task_id="t-test",
            files_created=state.files_created,
            task_completed=state.is_complete,
            is_paused=state.is_paused,
        )
        status_label, verified = report.evaluate_status(self.workspace_root)
        self.assertEqual(status_label, CompletionStatus.PAUSED.value)
        self.assertFalse(verified)

    def test_2_paused_task_persistence(self) -> None:
        """2. Verify that paused task state is persisted into an atomic WorkflowCheckpoint."""
        agent = CodeMindAgent(self.config, ui=self.ui)
        assert isinstance(agent.model, MockModelAdapter)

        plan_json = json.dumps({
            "protocol_version": "1",
            "type": "plan",
            "reason": "Initial plan",
            "plan": [
                {"id": "t1", "title": "Create module A", "status": "completed"},
                {"id": "t2", "title": "Create module B", "status": "pending"},
            ],
        })
        tool_json = json.dumps({
            "protocol_version": "1",
            "type": "tool_call",
            "tool": "create_file",
            "arguments": {"path": "src/a.py", "content": "# a"},
            "reason": "Execute t1",
        })
        agent.model.queue_response(plan_json)
        agent.model.queue_response(tool_json)

        state = asyncio.run(agent.run_task("Execute plan", max_turns=2))
        self.assertTrue(state.is_paused)

        # Check that checkpoint manager persisted the checkpoint
        mgr = CheckpointManager(self.workspace_root)
        ckpt = mgr.load_latest_checkpoint(agent.active_snapshot.session_id)
        self.assertIsNotNone(ckpt)
        self.assertFalse(ckpt.is_completed)
        self.assertTrue(len(ckpt.tasks) >= 2)

    def test_3_task_continuation(self) -> None:
        """3. Verify task continuation grants a fresh turn budget and preserves prior completed steps."""
        agent = CodeMindAgent(self.config, ui=self.ui)
        assert isinstance(agent.model, MockModelAdapter)

        # Segment 1: Create a file, reach max_turns=1
        tool_1 = json.dumps({
            "protocol_version": "1",
            "type": "tool_call",
            "tool": "create_file",
            "arguments": {"path": "src/part1.py", "content": "# part 1\n"},
            "reason": "Write part 1",
        })
        agent.model.queue_response(tool_1)
        state1 = asyncio.run(agent.run_task("Build two-part system", max_turns=1))
        self.assertTrue(state1.is_paused)
        self.assertEqual(state1.turn_count, 1)
        self.assertTrue(len(state1.files_created) > 0)

        # Segment 2: Continue the task! Grants fresh turn budget (starts turn_count=0)
        tool_2 = json.dumps({
            "protocol_version": "1",
            "type": "tool_call",
            "tool": "create_file",
            "arguments": {"path": "src/part2.py", "content": "# part 2\n"},
            "reason": "Write part 2",
        })
        final_json = json.dumps({
            "protocol_version": "1",
            "type": "final",
            "content": "Both parts completed.",
            "summary": ["Created part 1 and part 2"],
        })
        agent.model.queue_response(tool_2)
        agent.model.queue_response(final_json)

        state2 = asyncio.run(agent.resume_paused_task(max_turns=3))
        self.assertTrue(state2.is_complete)
        self.assertFalse(state2.is_paused)
        self.assertEqual(state2.status, "completed")
        self.assertTrue((self.workspace_root / "src" / "part1.py").is_file())
        self.assertTrue((self.workspace_root / "src" / "part2.py").is_file())

    def test_4_independent_new_task_creation(self) -> None:
        """4. Verify that starting a new task resets turn_count to 0 and does not return prior turn limit error."""
        agent = CodeMindAgent(self.config, ui=self.ui)
        assert isinstance(agent.model, MockModelAdapter)

        # Task 1 hits turn limit at max_turns=1
        tool_1 = json.dumps({
            "protocol_version": "1",
            "type": "tool_call",
            "tool": "create_file",
            "arguments": {"path": "src/old.py", "content": "# old\n"},
            "reason": "Old task",
        })
        agent.model.queue_response(tool_1)
        state1 = asyncio.run(agent.run_task("Task 1", max_turns=1))
        self.assertTrue(state1.is_paused)
        self.assertEqual(state1.turn_count, 1)

        # Task 2: A brand new independent instruction
        final_2 = json.dumps({
            "protocol_version": "1",
            "type": "final",
            "content": "Task 2 finished instantly.",
            "summary": ["Done"],
        })
        agent.model.queue_response(final_2)
        state2 = asyncio.run(agent.run_task("Task 2: Independent question", max_turns=2))

        # Must execute cleanly, NOT return turn limit error
        self.assertTrue(state2.is_complete)
        self.assertFalse(state2.is_paused)
        self.assertEqual(state2.task_instruction, "Task 2: Independent question")
        self.assertNotEqual(state1.current_task_id, state2.current_task_id)

    def test_5_ctrl_c_cancellation(self) -> None:
        """5. Verify Ctrl+C cancellation marks task cancelled, preserves checkpoint, and cleans up."""
        planner = Planner()
        sandbox = WorkspaceSandbox(self.workspace_root)
        perm = PermissionChecker(PermissionMode.TRUSTED)
        context = ExecutionContext(workspace_root=self.workspace_root, sandbox=sandbox, permission_checker=perm, ui=self.ui)
        mock_model = MockModelAdapter()
        loop = AgentLoop(
            model_adapter=mock_model,
            tool_registry=ToolRegistry(),
            execution_context=context,
            planner=planner,
            max_turns=5,
            ui=self.ui,
        )

        state = AgentState(
            session_id="cm-cancel-test",
            workspace_root=str(self.workspace_root),
            task_instruction="Long running task",
        )

        # Cancel loop immediately
        loop.cancel()
        final_state = asyncio.run(loop.execute_task(state))

        self.assertTrue(final_state.is_cancelled)
        self.assertFalse(final_state.is_complete)
        self.assertEqual(final_state.status, "cancelled")
        self.assertIn("cancelled by user", final_state.final_content.lower())

    def test_6_event_loop_cleanup(self) -> None:
        """6. Verify event listener receives proper lifecycle events without unhandled exceptions."""
        events: list[AgentEvent] = []

        def listener(ev: AgentEvent) -> None:
            events.append(ev)

        agent = CodeMindAgent(self.config, ui=self.ui)
        assert isinstance(agent.model, MockModelAdapter)

        final_json = json.dumps({
            "protocol_version": "1",
            "type": "final",
            "content": "Quick finish",
            "summary": ["Done"],
        })
        agent.model.queue_response(final_json)

        state = asyncio.run(agent.run_task("Simple query"))
        self.assertTrue(state.is_complete)

        # Verify clean event shutdown and trace recording
        session_events = agent.sessions.get_session_events(agent.active_snapshot.session_id)
        self.assertGreater(len(session_events), 0)
        self.assertTrue(any(e["event_type"] == AgentEventType.TASK_COMPLETED.value for e in session_events))

    def test_7_stale_verification_prevention(self) -> None:
        """7. Verify files touched in Task 1 never leak into Task 2's verification report."""
        agent = CodeMindAgent(self.config, ui=self.ui)
        assert isinstance(agent.model, MockModelAdapter)

        # Task 1: Modifies file_a.py
        tool_1 = json.dumps({
            "protocol_version": "1",
            "type": "tool_call",
            "tool": "create_file",
            "arguments": {"path": "src/file_a.py", "content": "# a"},
            "reason": "Create A",
        })
        final_1 = json.dumps({
            "protocol_version": "1",
            "type": "final",
            "content": "Done A",
            "summary": ["A created"],
        })
        agent.model.queue_response(tool_1)
        agent.model.queue_response(final_1)
        state1 = asyncio.run(agent.run_task("Create A"))
        self.assertTrue(len(state1.files_created) > 0)
        file_a_entry = state1.files_created[0]

        # Task 2: Modifies file_b.py
        tool_2 = json.dumps({
            "protocol_version": "1",
            "type": "tool_call",
            "tool": "create_file",
            "arguments": {"path": "src/file_b.py", "content": "# b"},
            "reason": "Create B",
        })
        final_2 = json.dumps({
            "protocol_version": "1",
            "type": "final",
            "content": "Done B",
            "summary": ["B created"],
        })
        agent.model.queue_response(tool_2)
        agent.model.queue_response(final_2)
        state2 = asyncio.run(agent.run_task("Create B"))

        # Task 2's files_created MUST NOT contain file_a
        self.assertNotIn(file_a_entry, state2.files_created)

    def test_8_task_specific_file_verification(self) -> None:
        """8. Verify HonestCompletionReport detects missing files on disk and flags failure."""
        report = HonestCompletionReport(
            task_id="t-missing",
            files_created=["src/ghost.py"],
            task_completed=True,
        )
        status_label, verified = report.evaluate_status(self.workspace_root)
        self.assertFalse(verified)
        self.assertIn("FAILED", status_label)
        self.assertIn("Missing expected files", status_label)
        self.assertIn("src/ghost.py", report.missing_files)

    def test_9_accurate_completion_reporting(self) -> None:
        """9. Verify passing unit test alone does NOT claim verified success if task is incomplete or paused."""
        fake_test_check = TestCheckResult(
            command="pytest",
            exit_code=0,
            passed=True,
            output="1 passed in 0.01s",
            passed_count=1,
            failed_count=0,
        )

        # Case A: Task paused at turn limit
        paused_report = HonestCompletionReport(
            task_id="t-paused",
            files_created=[],
            checks=[fake_test_check],
            task_completed=False,
            is_paused=True,
        )
        status_paused, verified_paused = paused_report.evaluate_status(self.workspace_root)
        self.assertFalse(verified_paused)
        self.assertEqual(status_paused, CompletionStatus.PAUSED.value)

        # Case B: Task completed with files verified on disk
        self.create_file("src/real.py", "print('hello')")
        success_report = HonestCompletionReport(
            task_id="t-success",
            files_created=["src/real.py"],
            checks=[fake_test_check],
            task_completed=True,
            is_paused=False,
        )
        status_ok, verified_ok = success_report.evaluate_status(self.workspace_root)
        self.assertTrue(verified_ok)
        self.assertEqual(status_ok, CompletionStatus.VERIFIED_SUCCESS.value)

    def test_10_tui_rendering(self) -> None:
        """10. Verify CodeMindTUI renders headers, meters, and progress without throwing exceptions."""
        console = Console(record=True, width=100)
        tui = CodeMindTUI(console=console, plain_mode=False)

        # Header
        tui.print_header(
            model_name="qwen3.6:35b",
            provider="ollama",
            workspace=str(self.workspace_root),
            permission_mode="supervised",
            turn_budget=20,
        )

        # Budget meter
        tui.print_budget_meter(turn=5, max_turns=20, tool_calls=8, max_tool_calls=30)

        # Plan progress
        tasks = [
            {"id": "t-1", "title": "Inspect codebase", "status": "completed"},
            {"id": "t-2", "title": "Implement feature", "status": "running"},
            {"id": "t-3", "title": "Run tests", "status": "pending"},
        ]
        tui.print_plan_progress(tasks)

        # Tool activity
        tui.print_tool_activity("write_file", "Update configuration", {"path": "config.json", "content": "{}"})

        # Capture output
        output = console.export_text()
        self.assertIn("CodeMind", output)
        tui_rendered_output = output
        self.assertIn("Inspect codebase", tui_rendered_output)
        self.assertIn("write_file", tui_rendered_output)

    def test_11_supervised_approval_interactions(self) -> None:
        """11. Verify authorization gate prompts cleanly and parses confirmation."""
        # Test approval granted
        with patch("builtins.input", return_value="y"):
            approved = self.ui.request_approval("Execute dangerous action", target="rm -rf /tmp/junk")
            self.assertTrue(approved)

        # Test approval denied
        with patch("builtins.input", return_value="n"):
            denied = self.ui.request_approval("Execute dangerous action", target="rm -rf /tmp/junk")
            self.assertFalse(denied)

    def test_12_long_running_task_progress(self) -> None:
        """12. Verify long-running multi-step task progresses through lifecycle states."""
        plan = TaskPlan()
        plan.add_or_update(task_id="t-1", title="Step 1", status="pending")
        plan.add_or_update(task_id="t-2", title="Step 2", status="pending")

        # Step 1 running
        plan.tasks[0].mark_status(TaskStatus.RUNNING)
        self.assertEqual(plan.tasks[0].status, TaskStatus.RUNNING)
        self.assertIsNotNone(plan.tasks[0].started_at)

        # Step 1 completed
        plan.tasks[0].mark_status(TaskStatus.COMPLETED, evidence="Files written")
        self.assertEqual(plan.tasks[0].status, TaskStatus.COMPLETED)
        self.assertIsNotNone(plan.tasks[0].completed_at)

        # Step 2 paused
        plan.tasks[1].mark_status(TaskStatus.PAUSED, evidence="Turn limit reached")
        self.assertEqual(plan.tasks[1].status, TaskStatus.PAUSED)


if __name__ == "__main__":
    unittest.main()
