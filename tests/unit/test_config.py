"""Unit tests for configuration loading and validation."""

import os
from pathlib import Path

from codemind.config import CodeMindConfig, ModelProvider, PermissionMode
from tests.base import BaseAgentTestCase


class TestConfig(BaseAgentTestCase):
    def test_default_config(self) -> None:
        cfg = CodeMindConfig.load(workspace_dir=self.workspace_root)
        self.assertEqual(Path(cfg.workspace_root).resolve(), self.workspace_root)
        self.assertEqual(cfg.security.permission_mode, PermissionMode.SUPERVISED)
        self.assertEqual(cfg.model.provider, ModelProvider.OLLAMA)
        self.assertEqual(cfg.model.model_name, "qwen3.6:35b")
        self.assertFalse(cfg.plain_mode)

    def test_env_var_overrides(self) -> None:
        os.environ["CODEMIND_MODEL"] = "custom-codemind-30b"
        os.environ["CODEMIND_ENDPOINT"] = "http://127.0.0.1:9000/v1"
        os.environ["CODEMIND_MODE"] = "read-only"
        os.environ["CODEMIND_PLAIN"] = "1"

        try:
            cfg = CodeMindConfig.load(workspace_dir=self.workspace_root)
            self.assertEqual(cfg.model.model_name, "custom-codemind-30b")
            self.assertEqual(cfg.model.endpoint, "http://127.0.0.1:9000/v1")
            self.assertEqual(cfg.security.permission_mode, PermissionMode.READ_ONLY)
            self.assertTrue(cfg.plain_mode)
        finally:
            del os.environ["CODEMIND_MODEL"]
            del os.environ["CODEMIND_ENDPOINT"]
            del os.environ["CODEMIND_MODE"]
            del os.environ["CODEMIND_PLAIN"]

    def test_json_config_file(self) -> None:
        cm_dir = self.workspace_root / ".codemind"
        cm_dir.mkdir(parents=True, exist_ok=True)
        cfg_file = cm_dir / "config.json"
        with open(cfg_file, "w") as f:
            f.write('{"model": {"model_name": "local-tested"}, "plain_mode": true}')

        cfg = CodeMindConfig.load(workspace_dir=self.workspace_root)
        self.assertEqual(cfg.model.model_name, "local-tested")
        self.assertTrue(cfg.plain_mode)
