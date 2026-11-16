"""Reliability regression tests for Model Gateway and Context Compaction (Phase B)."""

import asyncio
import unittest

from codemind.context.compactor import ContextCompactor
from codemind.models.base import (
    ChatMessage,
    ModelCapabilityProfile,
    ModelUnavailableError,
)
from codemind.models.custom import CodeMindCustomAdapter
from codemind.models.gateway import ModelGateway
from codemind.models.mock import MockModelAdapter
from codemind.models.ollama import OllamaAdapter
from codemind.planning.planner import Planner
from codemind.planning.task import TaskPlan, TaskStatus
from codemind.runtime.loop import AgentLoop
from codemind.runtime.state import AgentState
from codemind.tools.base import ExecutionContext
from codemind.tools.registry import ToolRegistry
from tests.base import BaseAgentTestCase


class TestGatewayAndCompaction(BaseAgentTestCase):
    def test_model_capability_profiles(self) -> None:
        """Verify explicit capability profile tracking across adapters."""
        mock = MockModelAdapter()
        ollama = OllamaAdapter()
        custom = CodeMindCustomAdapter()

        self.assertTrue(mock.capability_profile.is_mock)
        self.assertFalse(ollama.capability_profile.is_mock)
        self.assertFalse(custom.capability_profile.is_mock)

        self.assertTrue(ollama.capability_profile.is_local)
        self.assertTrue(custom.capability_profile.is_local)
        self.assertTrue(mock.capability_profile.supports_json_schema)
        self.assertTrue(ollama.capability_profile.supports_json_schema)

    def test_gateway_local_policy_enforcement(self) -> None:
        """Verify ModelGateway prevents silent cloud routing when local_only=True."""
        cloud_mock = MockModelAdapter(endpoint="https://api.openai.com/v1")
        with self.assertRaises(ModelUnavailableError) as ctx:
            ModelGateway(cloud_mock, local_only=True)
        self.assertIn("Policy Violation", str(ctx.exception))
        self.assertIn("api.openai.com", str(ctx.exception))

    def test_gateway_streaming_accumulation(self) -> None:
        """Verify ModelGateway assembles streaming chunks into a verified complete response."""
        mock = MockModelAdapter(responses=['{"type": "final", "content": "Done"}'])
        gateway = ModelGateway(mock, local_only=True)

        async def _test():
            return await gateway.accumulate_stream([ChatMessage(role="user", content="Hello")])

        assembled = asyncio.run(_test())
        self.assertIn('"type": "final"', assembled)
        self.assertIn('"content": "Done"', assembled)

    def test_context_compactor_preserves_invariants(self) -> None:
        """Verify ContextCompactor preserves original request, recent turns, and plan state."""
        compactor = ContextCompactor(threshold_chars=500, keep_recent_turns=2)

        plan = TaskPlan()
        plan.add_or_update("t1", "Inspect DB", status=TaskStatus.COMPLETED)
        plan.add_or_update("t2", "Add Auth", status=TaskStatus.RUNNING)

        # Build a conversation with system msg, user request, several tool observations, and recent turns
        messages = [
            ChatMessage(role="system", content="System Prompt Instructions"),
            ChatMessage(role="user", content="Original User Goal: Build auth microservice"),
            ChatMessage(role="assistant", content='{"type": "tool_call", "tool": "read_file", "arguments": {"path": "src/db.py"}}'),
            ChatMessage(role="user", content="Observation: " + "X" * 300),  # long output
            ChatMessage(role="assistant", content='{"type": "tool_call", "tool": "read_file", "arguments": {"path": "src/models.py"}}'),
            ChatMessage(role="user", content="Observation: " + "Y" * 300),  # long output
            ChatMessage(role="assistant", content='{"type": "plan", "plan": []}'),
            ChatMessage(role="user", content="Proceed with plan"),
        ]

        unverified = ["Integration tests not yet run"]
        res = compactor.compact(messages, task_plan=plan, unverified_notes=unverified, force=True)

        self.assertTrue(res.was_compacted)
        self.assertGreater(res.saved_chars, 0)

        # Invariant 1: System prompt is preserved unchanged
        self.assertEqual(res.messages[0].content, "System Prompt Instructions")

        # Invariant 2: Original user request is preserved unchanged
        self.assertEqual(res.messages[1].content, "Original User Goal: Build auth microservice")

        # Invariant 3: Recent 2 turns are preserved at the end
        self.assertEqual(res.messages[-2].content, messages[-2].content)
        self.assertEqual(res.messages[-1].content, messages[-1].content)

        # Invariant 4: Compacted summary message contains plan and unverified notes
        summary_content = res.messages[2].content
        self.assertIn("--- COMPACTED CONVERSATION SUMMARY ---", summary_content)
        self.assertIn("t1: Inspect DB", summary_content)
        self.assertIn("Integration tests not yet run", summary_content)

    def test_loop_auto_compaction(self) -> None:
        """Verify AgentLoop automatically invokes compaction when context exceeds threshold."""
        tools = ToolRegistry()
        planner = Planner()
        exec_ctx = ExecutionContext(
            workspace_root=self.workspace_root,
            sandbox=self.sandbox,
            permission_checker=self.permission_checker,
        )

        mock = MockModelAdapter(responses=['{"protocol_version": "1", "type": "final", "content": "Finished", "summary": []}'])
        compactor = ContextCompactor(threshold_chars=400, keep_recent_turns=2)

        loop = AgentLoop(
            model_adapter=mock,
            tool_registry=tools,
            execution_context=exec_ctx,
            planner=planner,
            max_turns=5,
            compactor=compactor,
        )

        state = AgentState(
            session_id="compaction-session",
            workspace_root=str(self.workspace_root),
            task_instruction="Long task",
            messages=[
                ChatMessage(role="system", content="System Prompt"),
                ChatMessage(role="user", content="User Instruction"),
                ChatMessage(role="assistant", content="Prior turn 1"),
                ChatMessage(role="user", content="Observation 1: " + "A" * 300),
                ChatMessage(role="assistant", content="Prior turn 2"),
                ChatMessage(role="user", content="Observation 2: " + "B" * 300),
                ChatMessage(role="assistant", content="Recent turn"),
                ChatMessage(role="user", content="Latest observation"),
            ],
            plan=planner.plan,
        )

        final_state = asyncio.run(loop.execute_task(state))
        self.assertTrue(final_state.is_complete)

        # Verify messages were compacted during execution
        has_summary = any("--- COMPACTED CONVERSATION SUMMARY ---" in m.content for m in final_state.messages)
        self.assertTrue(has_summary, "Invariant violation: Auto-compaction was not triggered in loop!")


if __name__ == "__main__":
    unittest.main()
