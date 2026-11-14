"""Unit tests for ModelDiscovery."""

import asyncio
from unittest.mock import AsyncMock, patch

from codemind.config import CodeMindConfig
from codemind.models.discovery import DiscoveredModel, ModelDiscovery
from tests.base import BaseAgentTestCase


class TestModelDiscovery(BaseAgentTestCase):
    def test_discovery_with_mock_models(self) -> None:
        mock_models = [
            {"name": "test-model-1", "size_bytes": 10737418240, "parameter_size": "7B", "family": "llama"},
            {"name": "test-model-2", "size_bytes": 21474836480, "parameter_size": "14B", "family": "qwen"},
        ]

        with patch.object(ModelDiscovery, "_probe_endpoint", new_callable=AsyncMock) as mock_probe:
            mock_probe.return_value = mock_models

            config = CodeMindConfig(workspace_root=str(self.workspace_root))
            discovered = asyncio.run(ModelDiscovery.discover_all(config))

            self.assertGreaterEqual(len(discovered), 2)
            names = [m.name for m in discovered]
            self.assertIn("test-model-1", names)
            self.assertIn("test-model-2", names)
            self.assertEqual(discovered[0].parameter_size, "7B")
            self.assertEqual(discovered[0].size_gb, 10.0)
