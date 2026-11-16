"""Integration tests for dynamic skill selection and execution within the agent loop."""

import asyncio
import json
from pathlib import Path

from codemind.config import CodeMindConfig, ModelProvider, PermissionMode
from codemind.models.mock import MockModelAdapter
from codemind.runtime.agent import CodeMindAgent
from tests.base import BaseAgentTestCase


class TestSkillsIntegration(BaseAgentTestCase):
    """Test dynamic skill selection, prompt injection, and execution within CodeMindAgent."""

    def test_agent_skill_selection_and_execution(self) -> None:
        """Verify that agent dynamically selects applicable skills and injects workflow into prompt."""
        async def _run() -> None:
            # Setup workspace manifests
            self.create_file("pyproject.toml", '[project]\nname = "store-api"\nversion = "0.1.0"\n')
            self.create_file("src/__init__.py", "")

            config = CodeMindConfig(
                workspace_root=str(self.workspace_root),
                plain_mode=True,
                model={"provider": ModelProvider.MOCK, "model_name": "mock-codemind"},
                security={"permission_mode": PermissionMode.TRUSTED},
            )
            agent = CodeMindAgent(config)
            await agent.initialize()

            # Mock responses
            r1 = json.dumps({
                "protocol_version": "1",
                "type": "plan",
                "plan": [
                    {"id": "t1", "title": "Inspect project structure", "status": "completed"},
                    {"id": "t2", "title": "Implement order router with type annotations", "status": "in_progress"},
                ],
                "reason": "Adhering to python-backend and api-development workflow",
            })
            r2 = json.dumps({
                "protocol_version": "1",
                "type": "tool_call",
                "tool": "create_file",
                "arguments": {
                    "path": "src/orders.py",
                    "content": "from __future__ import annotations\n\ndef get_order(order_id: int) -> dict[str, int]:\n    return {'id': order_id}\n",
                },
                "reason": "Create typed order router",
            })
            r3 = json.dumps({
                "protocol_version": "1",
                "type": "final",
                "content": "Created typed orders router in src/orders.py following python-backend guidelines.",
                "summary": ["Created src/orders.py with type annotations"],
            })

            assert isinstance(agent.model, MockModelAdapter)
            agent.model.queue_response(r1)
            agent.model.queue_response(r2)
            agent.model.queue_response(r3)

            instruction = "Implement a FastAPI order router endpoint with strict type annotations"
            state = await agent.run_task(instruction)

            self.assertTrue(state.is_complete)
            self.assertTrue((self.workspace_root / "src" / "orders.py").exists())

            # Check that prompt included active skills
            system_msg = state.messages[0].content
            self.assertIn("--- PROJECT SKILLS & GUIDELINES ---", system_msg)
            self.assertIn("python-backend", system_msg)
            self.assertIn("api-development", system_msg)
            self.assertIn("Authoritative Constraints", system_msg)

        asyncio.run(_run())
