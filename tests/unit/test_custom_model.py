"""Unit tests for CodeMindCustomAdapter, ProtocolNormalizer, and FallbackAwareModelAdapter."""

from __future__ import annotations

import asyncio
import json
import unittest

from codemind.config import ModelProvider, ModelSettings
from codemind.models import create_adapter
from codemind.models.base import (
    ChatMessage,
    ContextOverflowError,
    HealthStatus,
    ModelResponse,
    ModelTimeoutError,
    ModelUnavailableError,
)
from codemind.models.custom import CodeMindCustomAdapter, FallbackAwareModelAdapter, ProtocolNormalizer
from codemind.models.mock import MockModelAdapter


class TestCustomModelUnit(unittest.TestCase):
    def setUp(self):
        self.custom_adapter = CodeMindCustomAdapter(
            endpoint="http://127.0.0.1:8000/v1",
            model_name="codemind",
            context_window=1000,  # Small window for overflow testing
        )

    def test_custom_adapter_capabilities(self):
        """Verify explicit capability profile for custom foundation model."""
        profile = self.custom_adapter.capability_profile
        self.assertTrue(profile.supports_streaming)
        self.assertTrue(profile.supports_structured_output)
        self.assertTrue(profile.supports_system_messages)
        self.assertEqual(profile.context_window, 1000)

    def test_context_overflow_detection(self):
        """Verify ContextOverflowError is raised before network transmission when prompt exceeds window."""
        huge_text = "a" * 5000  # ~1250 tokens > 1000 limit
        messages = [ChatMessage(role="user", content=huge_text)]

        with self.assertRaises(ContextOverflowError):
            asyncio.run(self.custom_adapter.generate(messages))

    def test_protocol_normalizer_valid_tool_call(self):
        """Edge Case 1: Valid clean tool call passes through."""
        raw = '{"protocol_version": "1", "type": "tool_call", "tool": "read_file", "arguments": {"path": "src/app.py"}, "reason": "Inspect"}'
        normalized = ProtocolNormalizer.normalize_response_content(raw)
        data = json.loads(normalized)
        self.assertEqual(data["protocol_version"], "1")
        self.assertEqual(data["type"], "tool_call")
        self.assertEqual(data["tool"], "read_file")
        self.assertEqual(data["arguments"]["path"], "src/app.py")

    def test_protocol_normalizer_fenced_markdown_and_thinking(self):
        """Edge Case 2 & 9: Strip <think> tags and markdown json code fences."""
        raw = (
            "<think>Analyzing request to create file...</think>\n"
            "```json\n"
            '{"type": "tool_call", "tool": "create_file", "arguments": {"path": "src/x.py", "content": "x=1"}}\n'
            "```\n"
        )
        normalized = ProtocolNormalizer.normalize_response_content(raw)
        data = json.loads(normalized)
        self.assertEqual(data["protocol_version"], "1")
        self.assertEqual(data["type"], "tool_call")
        self.assertEqual(data["tool"], "create_file")

    def test_protocol_normalizer_missing_arguments(self):
        """Edge Case 3: Missing arguments dictionary is sanitized to empty dict."""
        raw = '{"protocol_version": "1", "type": "tool_call", "tool": "list_directory"}'
        normalized = ProtocolNormalizer.normalize_response_content(raw)
        data = json.loads(normalized)
        self.assertIn("arguments", data)
        self.assertEqual(data["arguments"], {})
        self.assertIn("reason", data)

    def test_protocol_normalizer_non_json_conversational(self):
        """Edge Case 6: Plain conversational text is safely converted to FinalAction."""
        raw = "I have completed inspecting the repository. Everything looks good!"
        normalized = ProtocolNormalizer.normalize_response_content(raw)
        data = json.loads(normalized)
        self.assertEqual(data["type"], "final")
        self.assertEqual(data["content"], raw)

    def test_protocol_normalizer_empty_response(self):
        """Edge Case 8: Empty or whitespace response converted to malformed action."""
        normalized = ProtocolNormalizer.normalize_response_content("   \n\t  ")
        data = json.loads(normalized)
        self.assertEqual(data["type"], "malformed")
        self.assertIn("empty", data["error"].lower())

    def test_fallback_aware_adapter_primary_success(self):
        """Verify FallbackAwareModelAdapter routes to primary when healthy."""
        mock_primary = MockModelAdapter(
            responses=['{"protocol_version": "1", "type": "final", "content": "Primary OK"}']
        )
        mock_fallback = MockModelAdapter(
            responses=['{"protocol_version": "1", "type": "final", "content": "Fallback OK"}']
        )

        composite = FallbackAwareModelAdapter(mock_primary, mock_fallback, enable_fallback=True)
        resp = asyncio.run(composite.generate([ChatMessage(role="user", content="Hi")]))

        self.assertIn("Primary OK", resp.content)
        self.assertEqual(len(composite.fallback_history), 0)

    def test_fallback_aware_adapter_on_primary_failure(self):
        """Verify FallbackAwareModelAdapter falls back and logs audit event when primary throws ModelUnavailableError."""
        mock_fallback = MockModelAdapter(
            responses=['{"protocol_version": "1", "type": "final", "content": "Fallback Served"}']
        )
        # Custom adapter pointing to unreachable port
        unreachable_custom = CodeMindCustomAdapter(
            endpoint="http://127.0.0.1:59999/v1",
            model_name="codemind",
            timeout_seconds=1,
        )

        composite = FallbackAwareModelAdapter(unreachable_custom, mock_fallback, enable_fallback=True)
        resp = asyncio.run(composite.generate([ChatMessage(role="user", content="Hi")]))

        self.assertIn("Fallback Served", resp.content)
        self.assertEqual(len(composite.fallback_history), 1)
        self.assertEqual(composite.fallback_history[0]["primary_model"], "codemind")
        self.assertEqual(composite.fallback_history[0]["fallback_model"], "mock-codemind")

    def test_factory_creates_fallback_composite(self):
        """Verify create_adapter returns FallbackAwareModelAdapter for CODEMIND_CUSTOM with fallback."""
        settings = ModelSettings(
            provider=ModelProvider.CODEMIND_CUSTOM,
            model_name="codemind",
            endpoint="http://127.0.0.1:8000/v1",
            fallback_provider=ModelProvider.MOCK,
            fallback_model="mock-fallback",
            enable_fallback=True,
        )
        adapter = create_adapter(settings)
        self.assertIsInstance(adapter, FallbackAwareModelAdapter)
        self.assertIsInstance(adapter.primary, CodeMindCustomAdapter)
        self.assertIsInstance(adapter.fallback, MockModelAdapter)


if __name__ == "__main__":
    unittest.main()
