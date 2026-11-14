"""Unit tests for model adapters and capability profiles."""

import asyncio
import unittest

from codemind.config import ModelProvider, ModelSettings
from codemind.models import create_adapter
from codemind.models.base import ChatMessage
from codemind.models.mock import MockModelAdapter


class TestModels(unittest.TestCase):
    def test_mock_adapter_generation(self) -> None:
        mock = MockModelAdapter(
            responses=['{"protocol_version": "1", "type": "final", "content": "Success"}']
        )
        msg = [ChatMessage(role="user", content="Hi")]
        resp = asyncio.run(mock.generate(msg))
        self.assertEqual(resp.content, '{"protocol_version": "1", "type": "final", "content": "Success"}')
        self.assertIsNotNone(resp.usage)

    def test_mock_adapter_health(self) -> None:
        mock = MockModelAdapter()
        health = asyncio.run(mock.check_health())
        self.assertTrue(health.healthy)
        self.assertEqual(health.details.get("mode"), "mock")

    def test_create_adapter_factory(self) -> None:
        settings_mock = ModelSettings(provider=ModelProvider.MOCK)
        adapter_mock = create_adapter(settings_mock)
        self.assertIsInstance(adapter_mock, MockModelAdapter)

        settings_local = ModelSettings(provider=ModelProvider.CODEMIND_LOCAL)
        adapter_local = create_adapter(settings_local)
        self.assertEqual(adapter_local.capability_profile.context_window, 32768)
