"""Reliability regression tests for turn budgets and pause bounds (REL-08, REL-09)."""

import asyncio
import unittest

from codemind.cli.ui import TerminalUI
from codemind.config import CodeMindConfig, ModelProvider, PermissionMode
from codemind.models.base import ChatMessage
from codemind.models.mock import MockModelAdapter
from codemind.planning.planner import Planner
from codemind.runtime.agent import CodeMindAgent
from codemind.runtime.loop import AgentLoop
from codemind.runtime.state import AgentState
from codemind.tools.base import ExecutionContext
from codemind.tools.registry import ToolRegistry
from tests.base import BaseAgentTestCase


class TestTurnBudgetBounds(BaseAgentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config.security.permission_mode = PermissionMode.TRUSTED

    def test_rel_08_repair_budget_decoupling(self) -> None:
        """REL-08: Protocol formatting error loopbacks must NOT burn through the primary

        task execution budget. Turn count must only advance on real action attempts.
        """
        tools = ToolRegistry()
        ui = TerminalUI(plain_mode=True)
        exec_ctx = ExecutionContext(
            workspace_root=self.workspace_root,
            sandbox=self.sandbox,
            permission_checker=self.permission_checker,
            ui=ui,
        )
        planner = Planner()

        # Sequence: 2 malformed responses, then 1 valid final action
        responses = [
            "Oops, I forgot JSON format",  # Malformed 1
            "Still forgot JSON format",  # Malformed 2
            '{"protocol_version": "1", "type": "final", "content": "Finally succeeded", "summary": []}',  # Valid final
        ]
        mock_model = MockModelAdapter(responses=responses)

        loop = AgentLoop(
            model_adapter=mock_model,
            tool_registry=tools,
            execution_context=exec_ctx,
            planner=planner,
            max_turns=5,
            ui=ui,
        )

        state = AgentState(
            session_id="test-repair-session",
            workspace_root=str(self.workspace_root),
            task_instruction="Execute instruction",
            messages=[ChatMessage(role="user", content="Execute instruction")],
            plan=planner.plan,
        )

        final_state = asyncio.run(loop.execute_task(state))

        # Invariant: Turn count should be 1 (for the final action), NOT 3!
        self.assertTrue(final_state.is_complete)
        self.assertEqual(
            final_state.turn_count,
            1,
            f"Invariant violation: Protocol repairs burned {final_state.turn_count} execution turns instead of 1!",
        )

    def test_rel_09_clean_pause_on_turn_limit_exhaustion(self) -> None:
        """REL-09: When task reaches the maximum turn limit without completion,

        it must transition cleanly to PAUSED with is_complete=False.
        """
        tools = ToolRegistry()
        ui = TerminalUI(plain_mode=True)
        exec_ctx = ExecutionContext(
            workspace_root=self.workspace_root,
            sandbox=self.sandbox,
            permission_checker=self.permission_checker,
            ui=ui,
        )
        planner = Planner()

        # Generate 10 plan actions that never reach 'final'
        responses = [
            f'{{"protocol_version": "1", "type": "plan", "plan": [{{"id": "t{i}", "title": "Step {i}", "status": "pending"}}], "reason": "Iterating step {i}"}}'
            for i in range(10)
        ]
        mock_model = MockModelAdapter(responses=responses)

        loop = AgentLoop(
            model_adapter=mock_model,
            tool_registry=tools,
            execution_context=exec_ctx,
            planner=planner,
            max_turns=5,  # Bound to 5 turns
            ui=ui,
        )

        state = AgentState(
            session_id="test-pause-session",
            workspace_root=str(self.workspace_root),
            task_instruction="Never ending plan",
            messages=[ChatMessage(role="user", content="Never ending plan")],
            plan=planner.plan,
        )

        final_state = asyncio.run(loop.execute_task(state))

        # Invariant: Must be paused, not complete
        self.assertFalse(final_state.is_complete, "Invariant violation: Exhausted turn task marked complete!")
        self.assertTrue(final_state.is_paused, "Invariant violation: Exhausted turn task was not marked paused!")
        self.assertEqual(final_state.status, "paused")
        self.assertEqual(final_state.turn_count, 5)


if __name__ == "__main__":
    unittest.main()
