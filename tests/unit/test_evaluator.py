"""Unit tests for ModelCapabilityTester."""

import asyncio

from codemind.models.evaluator import ModelCapabilityTester
from codemind.models.mock import MockModelAdapter
from tests.base import BaseAgentTestCase


class TestEvaluator(BaseAgentTestCase):
    def test_evaluator_with_mock_model(self) -> None:
        responses = [
            "CODEMIND_OK",  # Probe 1: Instruction following
            '{"status": "success", "code": 200}',  # Probe 2: Structured JSON
            '{"protocol_version": "1", "type": "tool_call", "tool": "read_file", "arguments": {"path": "src/main.py"}, "reason": "Inspect"}',  # Probe 3: Tool calling
            "COMPILED_FIRST: Alpha",  # Probe 4: Reasoning
            "The port is 9988",  # Probe 5: Context
            "def calculate_factorial(n: int) -> int:\n    return 1\n",  # Probe 6: Code gen
            "ERROR_TYPE: IndexError",  # Probe 7: Error interp
        ]
        adapter = MockModelAdapter(responses=responses)
        tester = ModelCapabilityTester(adapter)

        result = asyncio.run(tester.evaluate_all())

        self.assertEqual(result.connection_status, "Available")
        self.assertEqual(len(result.probes), 7)
        for p in result.probes:
            self.assertTrue(p.passed, f"Probe '{p.dimension}' failed: {p.details}")

        self.assertIn("Full", result.compatibility_rating)
        self.assertTrue(result.recommended_for_agent)
