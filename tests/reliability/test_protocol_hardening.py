"""Reliability regression tests for protocol hardening (REL-06, REL-07)."""

import unittest

from codemind.models.protocol import (
    FinalAction,
    MalformedAction,
    ProtocolParser,
    ToolCallAction,
)


class TestProtocolHardening(unittest.TestCase):
    def test_rel_06_conversational_markdown_fencing(self) -> None:
        """REL-06: Model emits text preamble and postamble around a fenced JSON block.

        ProtocolParser must cleanly extract and parse the envelope without error.
        """
        raw_output = (
            "Certainly! I will now inspect the project structure to understand the application layout.\n\n"
            "```json\n"
            "{\n"
            '  "protocol_version": "1",\n'
            '  "type": "tool_call",\n'
            '  "tool": "list_directory",\n'
            '  "arguments": {"path": "src"},\n'
            '  "reason": "Inspect source directory contents"\n'
            "}\n"
            "```\n\n"
            "Please confirm if you would like me to proceed with further analysis."
        )

        action = ProtocolParser.parse(raw_output)
        self.assertIsInstance(action, ToolCallAction)
        self.assertEqual(action.tool, "list_directory")
        self.assertEqual(action.arguments, {"path": "src"})
        self.assertEqual(action.reason, "Inspect source directory contents")

    def test_rel_07_non_json_hallucination_cannot_trigger_tools(self) -> None:
        """REL-07: Model emits pure conversational prose without a structured JSON envelope.

        Must return MalformedAction and strictly forbid tool invocation.
        """
        raw_prose = (
            "I have looked at the project and I recommend that you run `npm install` and create "
            "a file called `src/App.jsx`. Let me know if you would like me to write it."
        )

        action = ProtocolParser.parse(raw_prose)
        self.assertIsInstance(action, MalformedAction)
        self.assertNotIsInstance(action, ToolCallAction)
        self.assertIn("did not contain a valid JSON envelope", action.correction_prompt)

    def test_missing_protocol_version_normalized(self) -> None:
        """Model emits a valid tool_call envelope but omits protocol_version.

        ProtocolParser must normalize protocol_version to '1'.
        """
        raw = (
            "```json\n"
            "{\n"
            '  "type": "tool_call",\n'
            '  "tool": "read_file",\n'
            '  "arguments": {"path": "README.md"},\n'
            '  "reason": "Read readme"\n'
            "}\n"
            "```"
        )
        action = ProtocolParser.parse(raw)
        self.assertIsInstance(action, ToolCallAction)
        self.assertEqual(action.protocol_version, "1")
        self.assertEqual(action.tool, "read_file")

    def test_trailing_comma_resilience(self) -> None:
        """Model outputs JSON with trailing commas (common in LLM generation).

        ProtocolParser must parse cleanly rather than emitting MalformedAction.
        """
        raw = (
            "```json\n"
            "{\n"
            '  "protocol_version": "1",\n'
            '  "type": "final",\n'
            '  "content": "All tasks completed.",\n'
            '  "summary": ["Step 1 done",],\n'
            "}\n"
            "```"
        )
        action = ProtocolParser.parse(raw)
        self.assertIsInstance(action, FinalAction)
        self.assertEqual(action.content, "All tasks completed.")
        self.assertEqual(action.summary, ["Step 1 done"])


if __name__ == "__main__":
    unittest.main()
