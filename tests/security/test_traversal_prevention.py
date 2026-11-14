"""Security tests ensuring workspace sandboxing prevents directory traversal and unauthorized modifications."""

import asyncio

from codemind.tools.base import ExecutionContext
from codemind.tools.filesystem import CreateFileTool, ReadFileTool
from codemind.tools.patch import ApplyPatchTool
from tests.base import BaseAgentTestCase


class TestTraversalPrevention(BaseAgentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.context = ExecutionContext(
            workspace_root=self.workspace_root,
            sandbox=self.sandbox,
            permission_checker=self.permission_checker,
        )

    def test_read_file_blocks_traversal(self) -> None:
        tool = ReadFileTool()
        res = asyncio.run(tool.execute({"path": "../../../etc/passwd"}, self.context))
        self.assertFalse(res.ok)
        self.assertEqual(res.error_code, "SECURITY_VIOLATION")

    def test_create_file_blocks_traversal(self) -> None:
        tool = CreateFileTool()
        res = asyncio.run(tool.execute({"path": "../external.py", "content": "malicious"}, self.context))
        self.assertFalse(res.ok)
        self.assertEqual(res.error_code, "SECURITY_VIOLATION")

    def test_apply_patch_blocks_traversal(self) -> None:
        tool = ApplyPatchTool()
        res = asyncio.run(
            tool.execute(
                {"path": "../../etc/hosts", "target": "127.0.0.1", "replacement": "0.0.0.0"},
                self.context,
            )
        )
        self.assertFalse(res.ok)
        self.assertEqual(res.error_code, "SECURITY_VIOLATION")
