"""Base test fixture providing isolated workspace environments."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from codemind.config import CodeMindConfig, ModelProvider, PermissionMode
from codemind.security.permissions import PermissionChecker
from codemind.security.sandbox import WorkspaceSandbox


class BaseAgentTestCase(unittest.TestCase):
    """Base test case providing clean isolated workspace sandbox."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="codemind_test_")
        self.workspace_root = Path(self.temp_dir).resolve()

        self.config = CodeMindConfig(
            workspace_root=str(self.workspace_root),
            plain_mode=True,
            model={"provider": ModelProvider.MOCK, "model_name": "mock-codemind"},
            security={"permission_mode": PermissionMode.SUPERVISED},
        )
        self.sandbox = WorkspaceSandbox(self.workspace_root)
        self.permission_checker = PermissionChecker(mode=PermissionMode.SUPERVISED)

    def tearDown(self) -> None:
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_file(self, rel_path: str, content: str) -> Path:
        """Helper to create sample project files inside test workspace."""
        target = self.workspace_root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
        return target
