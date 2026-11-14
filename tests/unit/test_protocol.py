"""Unit tests for ProtocolParser and v1 envelope validation."""

import unittest

from codemind.models.protocol import (
    FinalAction,
    MalformedAction,
    PlanAction,
    ProtocolParser,
    ToolCallAction,
)


class TestProtocol(unittest.TestCase):
    def test_parse_tool_call(self) -> None:
        raw = '{"protocol_version": "1", "type": "tool_call", "tool": "read_file", "arguments": {"path": "src/main.py"}, "reason": "Inspect entrypoint"}'
        action = ProtocolParser.parse(raw)
        self.assertIsInstance(action, ToolCallAction)
        self.assertEqual(action.tool, "read_file")
        self.assertEqual(action.arguments, {"path": "src/main.py"})
        self.assertEqual(action.reason, "Inspect entrypoint")

    def test_parse_fenced_json(self) -> None:
        raw = (
            "Here is the plan:\n"
            "```json\n"
            "{\n"
            '  "protocol_version": "1",\n'
            '  "type": "plan",\n'
            '  "plan": [{"id": "t1", "title": "Check code", "status": "pending"}],\n'
            '  "reason": "Initial plan"\n'
            "}\n"
            "```"
        )
        action = ProtocolParser.parse(raw)
        self.assertIsInstance(action, PlanAction)
        self.assertEqual(len(action.plan), 1)
        self.assertEqual(action.plan[0].id, "t1")

    def test_parse_final_action(self) -> None:
        raw = '{"protocol_version": "1", "type": "final", "content": "Done!", "summary": ["step 1"]}'
        action = ProtocolParser.parse(raw)
        self.assertIsInstance(action, FinalAction)
        self.assertEqual(action.content, "Done!")
        self.assertEqual(action.summary, ["step 1"])

    def test_parse_malformed_non_json(self) -> None:
        raw = "I am a helpful assistant and I read your file."
        action = ProtocolParser.parse(raw)
        self.assertIsInstance(action, MalformedAction)
        self.assertIn("did not contain a valid JSON envelope", action.correction_prompt)

    def test_unsupported_protocol_version(self) -> None:
        raw = '{"protocol_version": "99", "type": "final", "content": "Hello"}'
        action = ProtocolParser.parse(raw)
        self.assertIsInstance(action, MalformedAction)
        self.assertIn("Unsupported protocol_version", action.validation_error)

    def test_invalid_type(self) -> None:
        raw = '{"protocol_version": "1", "type": "unknown_action", "content": "Hello"}'
        action = ProtocolParser.parse(raw)
        self.assertIsInstance(action, MalformedAction)
        self.assertIn("Unknown action type", action.validation_error)
