"""Integration test for persistent memory retrieval and cross-session recall."""

import asyncio
import json
from pathlib import Path

from codemind.config import CodeMindConfig, ModelProvider, PermissionMode
from codemind.models.mock import MockModelAdapter
from codemind.runtime.agent import CodeMindAgent
from codemind.runtime.state import AgentState
from codemind.verification.reporter import TestCheckResult, HonestCompletionReport
from tests.base import BaseAgentTestCase


class TestMemoryIntegration(BaseAgentTestCase):
    """Test cross-session recall and prompt injection across discrete agent runs."""

    def test_cross_session_memory_recall(self) -> None:
        """Verify that knowledge distilled from Session 1 is recalled in Session 2."""
        async def _run() -> None:
            # 1. Run Session 1
            config1 = CodeMindConfig(
                workspace_root=str(self.workspace_root),
                plain_mode=True,
                model={"provider": ModelProvider.MOCK, "model_name": "mock-codemind"},
                security={"permission_mode": PermissionMode.TRUSTED},
            )
            agent1 = CodeMindAgent(config1)
            await agent1.initialize()

            # Set up mock model response for Session 1: create src/calc.py and finish
            tool_call_json = json.dumps({
                "protocol_version": "1",
                "type": "tool_call",
                "tool": "create_file",
                "arguments": {"path": "src/calc.py", "content": "def add(a, b): return a + b\n"},
                "reason": "Create basic calculator module",
            })
            final_json = json.dumps({
                "protocol_version": "1",
                "type": "final",
                "content": "Calculator module created successfully.",
                "summary": ["Created src/calc.py with add function"],
            })

            # Mock adapter responses
            assert isinstance(agent1.model, MockModelAdapter)
            agent1.model.queue_response(tool_call_json)
            agent1.model.queue_response(final_json)

            state1 = await agent1.run_task("Implement calculator module in src/calc.py")
            self.assertTrue(state1.is_complete)
            self.assertTrue((self.workspace_root / "src" / "calc.py").exists())

            # Verify memory was persisted
            stats = agent1.memory.get_stats()
            self.assertGreater(stats.total_entries, 0)
            task_entries = agent1.memory.list_entries(layer="task")
            self.assertEqual(len(task_entries), 1)
            self.assertIn("src/calc.py", task_entries[0].metadata["files"])

            # 2. Session 2: Fresh agent instance with new session ID
            config2 = CodeMindConfig(
                workspace_root=str(self.workspace_root),
                plain_mode=True,
                model={"provider": ModelProvider.MOCK, "model_name": "mock-codemind"},
                security={"permission_mode": PermissionMode.TRUSTED},
            )
            agent2 = CodeMindAgent(config2)
            await agent2.initialize()

            # Verify that retriever finds the prior task memory
            recalled_context = agent2.retriever.retrieve_context("calc add function")
            self.assertIn("Relevant Prior Tasks & Operational History (Layer C)", recalled_context)
            self.assertIn("src/calc.py", recalled_context)

            # Check system prompt assembly in Agent 2 includes persistent memory block
            summary = agent2.discovery.analyze()
            system_prompt = agent2.budget.assemble_system_prompt(
                base_instructions="Base instructions",
                tool_definitions="Tools",
                project_summary=summary,
                memory_text=recalled_context,
            )
            self.assertIn("--- PERSISTENT PROJECT MEMORY ---", system_prompt)
            self.assertIn("src/calc.py", system_prompt)

        asyncio.run(_run())
