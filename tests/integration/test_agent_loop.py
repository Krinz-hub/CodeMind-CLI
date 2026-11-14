"""Integration test for full multi-turn AgentLoop execution."""

import asyncio

from codemind.cli.ui import TerminalUI
from codemind.models.mock import MockModelAdapter
from codemind.planning.planner import Planner
from codemind.runtime.loop import AgentLoop
from codemind.runtime.state import AgentState
from codemind.security.permissions import PermissionChecker, PermissionLevel, PermissionMode
from codemind.tools.base import ExecutionContext
from codemind.tools.registry import ToolRegistry
from tests.base import BaseAgentTestCase


class TestAgentLoopIntegration(BaseAgentTestCase):
    def test_full_loop_workflow(self) -> None:
        # Create a file for the mock model to inspect
        self.create_file("src/app.py", "def add(a, b): return a + b\n")

        # Program mock model responses
        # Turn 1: Propose plan
        r1 = (
            '{"protocol_version": "1", "type": "plan", '
            '"plan": [{"id": "t1", "title": "Inspect code", "status": "in_progress"}], '
            '"reason": "Start task"}'
        )
        # Turn 2: Request read_file tool
        r2 = (
            '{"protocol_version": "1", "type": "tool_call", "tool": "read_file", '
            '"arguments": {"path": "src/app.py"}, "reason": "Inspect add function"}'
        )
        # Turn 3: Emit final completion
        r3 = (
            '{"protocol_version": "1", "type": "final", '
            '"content": "Found add function in src/app.py.", '
            '"summary": ["Inspected src/app.py", "Identified add function"]}'
        )

        mock_adapter = MockModelAdapter(responses=[r1, r2, r3])
        tools = ToolRegistry()
        ui = TerminalUI(plain_mode=True)

        perm_checker = PermissionChecker(mode=PermissionMode.TRUSTED)
        context = ExecutionContext(
            workspace_root=self.workspace_root,
            sandbox=self.sandbox,
            permission_checker=perm_checker,
            ui=ui,
        )

        planner = Planner()
        loop = AgentLoop(
            model_adapter=mock_adapter,
            tool_registry=tools,
            execution_context=context,
            planner=planner,
            max_turns=10,
            ui=ui,
        )

        state = AgentState(
            session_id="cm-int-test-1",
            workspace_root=str(self.workspace_root),
            task_instruction="Inspect the codebase",
        )

        final_state = asyncio.run(loop.execute_task(state))

        self.assertTrue(final_state.is_complete)
        self.assertEqual(final_state.total_tool_calls, 1)
        self.assertIn("Found add function", final_state.final_content)
        self.assertEqual(len(final_state.final_summary), 2)
