"""Unit tests for filesystem, search, patch, and terminal tools."""

import asyncio

from codemind.tools.base import ExecutionContext
from codemind.tools.filesystem import CreateFileTool, ListDirectoryTool, ReadFileTool
from codemind.tools.patch import ApplyPatchTool
from codemind.tools.search import SearchFilesTool, SearchTextTool
from codemind.tools.terminal import RunCommandTool
from tests.base import BaseAgentTestCase


class TestTools(BaseAgentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.context = ExecutionContext(
            workspace_root=self.workspace_root,
            sandbox=self.sandbox,
            permission_checker=self.permission_checker,
        )

    def test_create_and_read_file(self) -> None:
        create_tool = CreateFileTool()
        read_tool = ReadFileTool()

        res_create = asyncio.run(create_tool.execute({"path": "src/app.py", "content": "x = 10\ny = 20\n"}, self.context))
        self.assertTrue(res_create.ok)
        self.assertTrue((self.workspace_root / "src/app.py").is_file())

        res_read = asyncio.run(read_tool.execute({"path": "src/app.py", "offset": 1, "limit": 10}, self.context))
        self.assertTrue(res_read.ok)
        self.assertIn("x = 10", res_read.content)
        self.assertIn("1 |", res_read.content)

    def test_apply_patch_tool(self) -> None:
        self.create_file("utils.py", "def greet():\n    return 'hello'\n")
        patch_tool = ApplyPatchTool()

        res = asyncio.run(
            patch_tool.execute(
                {
                    "path": "utils.py",
                    "target": "    return 'hello'",
                    "replacement": "    return 'hello, world!'",
                },
                self.context,
            )
        )
        self.assertTrue(res.ok)
        with open(self.workspace_root / "utils.py") as f:
            updated = f.read()
        self.assertIn("return 'hello, world!'", updated)

    def test_search_files_and_text(self) -> None:
        self.create_file("module_a.py", "# unique_search_keyword")
        self.create_file("sub/module_b.py", "# another line")

        search_files = SearchFilesTool()
        res_files = asyncio.run(search_files.execute({"pattern": "*.py"}, self.context))
        self.assertTrue(res_files.ok)
        self.assertIn("module_a.py", res_files.content)

        search_text = SearchTextTool()
        res_text = asyncio.run(search_text.execute({"query": "unique_search_keyword"}, self.context))
        self.assertTrue(res_text.ok)
        self.assertIn("module_a.py:1:", res_text.content)

    def test_run_command_tool(self) -> None:
        term_tool = RunCommandTool()
        res = asyncio.run(term_tool.execute({"command": "echo 'Testing CodeMind'"}, self.context))
        self.assertTrue(res.ok)
        self.assertIn("Testing CodeMind", res.stdout)
        self.assertEqual(res.exit_code, 0)
