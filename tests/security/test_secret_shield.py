"""Security tests ensuring sensitive files (.env, keys, tokens) are shielded."""

import asyncio

from codemind.tools.base import ExecutionContext
from codemind.tools.filesystem import ReadFileTool
from tests.base import BaseAgentTestCase


class TestSecretShield(BaseAgentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.context = ExecutionContext(
            workspace_root=self.workspace_root,
            sandbox=self.sandbox,
            permission_checker=self.permission_checker,
        )

    def test_blocks_reading_dot_env(self) -> None:
        self.create_file(".env", "DATABASE_URL=postgres://root:password@localhost/db")
        tool = ReadFileTool()
        res = asyncio.run(tool.execute({"path": ".env"}, self.context))
        self.assertFalse(res.ok)
        self.assertEqual(res.error_code, "SECURITY_VIOLATION")

    def test_blocks_reading_pem_files(self) -> None:
        self.create_file("server.key", "-----BEGIN PRIVATE KEY-----xyz-----END PRIVATE KEY-----")
        tool = ReadFileTool()
        res = asyncio.run(tool.execute({"path": "server.key"}, self.context))
        self.assertFalse(res.ok)
        self.assertEqual(res.error_code, "SECURITY_VIOLATION")
