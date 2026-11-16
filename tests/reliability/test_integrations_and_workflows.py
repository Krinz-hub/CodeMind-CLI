"""Hermetic regression tests for Phase D: Integrations & Workflows.

Covers:
- REL-11: MCP Client, stdio transport, tool discovery, invocation, and server lifecycle (Workstream I)
- REL-12: Git branch manipulation, safe staging, secret commit prevention, and log history (Workstream J)
- REL-13: Fine-grained declarative security policies with command and path constraints (Workstream K)
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock

from codemind.config import CodeMindConfig, PermissionMode
from codemind.mcp.client import MCPClient
from codemind.mcp.manager import MCPManager
from codemind.mcp.models import MCPServerConfig, MCPToolDefinition
from codemind.mcp.tool import MCPProxyTool, make_mcp_args_schema
from codemind.security.permissions import (
    PermissionChecker,
    PermissionLevel,
    PermissionPolicyEngine,
    PermissionRule,
    PolicyDecision,
)
from codemind.security.sandbox import WorkspaceSandbox
from codemind.tools.base import ExecutionContext
from codemind.tools.git import GitBranchTool, GitCommitTool, GitDiffTool, GitLogTool, GitStatusTool
from codemind.tools.registry import ToolRegistry
from tests.base import BaseAgentTestCase


class TestIntegrationsAndWorkflows(BaseAgentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.config = CodeMindConfig.load(
            self.workspace_root,
            overrides={"security": {"permission_mode": "trusted"}},
        )
        self.registry = ToolRegistry()
        self.sandbox = WorkspaceSandbox(self.workspace_root)
        self.context = ExecutionContext(
            workspace_root=self.workspace_root,
            sandbox=self.sandbox,
            permission_checker=PermissionChecker(mode=PermissionMode.TRUSTED),
        )

    # -------------------------------------------------------------------------
    # Workstream I: MCP Integration Tests
    # -------------------------------------------------------------------------

    def test_mcp_args_schema_generation(self) -> None:
        """Verify dynamic argument schema creation and validation from MCP inputSchema."""
        schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        }
        model_cls = make_mcp_args_schema("echo_tool", schema)
        self.assertEqual(model_cls.model_json_schema(), schema)

        # Valid arguments
        valid = model_cls.model_validate({"query": "hello", "limit": 10})
        self.assertEqual(valid.query, "hello")

        # Missing required argument
        with self.assertRaises(ValueError) as ctx:
            model_cls.model_validate({"limit": 5})
        self.assertIn("Missing required argument", str(ctx.exception))

    def test_mcp_manager_config_lifecycle(self) -> None:
        """Verify MCPManager adding, enabling, disabling, and removing servers."""
        mgr = MCPManager(self.workspace_root)
        self.assertEqual(len(mgr.load_config().mcpServers), 0)

        # Add server
        s = mgr.add_server(
            name="local_eval",
            command="python3",
            args=["eval_server.py"],
            disabled=False,
        )
        self.assertEqual(s.name, "local_eval")
        self.assertTrue(mgr.config_file.is_file())

        # List servers
        listed = mgr.list_servers()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["name"], "local_eval")
        self.assertFalse(listed[0]["disabled"])

        # Disable server
        self.assertTrue(mgr.disable_server("local_eval"))
        self.assertTrue(mgr.list_servers()[0]["disabled"])

        # Enable server
        self.assertTrue(mgr.enable_server("local_eval"))
        self.assertFalse(mgr.list_servers()[0]["disabled"])

        # Remove server
        self.assertTrue(mgr.remove_server("local_eval"))
        self.assertEqual(len(mgr.list_servers()), 0)

    def test_mcp_client_stdio_handshake_and_invocation(self) -> None:
        """Test full stdio JSON-RPC handshake and tool execution with a real Python subprocess."""
        # Create a lightweight Python MCP mock server script
        mock_server_code = """
import sys, json

while True:
    line = sys.stdin.readline()
    if not line:
        break
    try:
        req = json.loads(line)
        method = req.get("method")
        req_id = req.get("id")

        if method == "initialize":
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "mock-mcp", "version": "1.0.0"}
                }
            }
            sys.stdout.write(json.dumps(res) + "\\n")
            sys.stdout.flush()
        elif method == "tools/list":
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "calculate",
                            "description": "Performs addition",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                                "required": ["a", "b"]
                            }
                        }
                    ]
                }
            }
            sys.stdout.write(json.dumps(res) + "\\n")
            sys.stdout.flush()
        elif method == "tools/call":
            params = req.get("params", {})
            args = params.get("arguments", {})
            total = args.get("a", 0) + args.get("b", 0)
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Result: {total}"}],
                    "isError": False
                }
            }
            sys.stdout.write(json.dumps(res) + "\\n")
            sys.stdout.flush()
    except Exception as ex:
        pass
"""
        server_path = self.create_file("mock_mcp_server.py", mock_server_code)

        config = MCPServerConfig(
            name="test_math",
            command=sys.executable,
            args=[str(server_path)],
        )
        client = MCPClient(config)

        async def _run() -> None:
            try:
                # 1. Start and handshake
                await client.start()
                self.assertTrue(client.is_running)

                # 2. List tools
                tools = await client.list_tools()
                self.assertEqual(len(tools), 1)
                self.assertEqual(tools[0].name, "calculate")

                # 3. Wrap in MCPProxyTool and execute
                proxy = MCPProxyTool("test_math", tools[0], client)
                res = await proxy.execute({"a": 15, "b": 27}, self.context)
                self.assertTrue(res.ok)
                self.assertIn("Result: 42", res.content)
            finally:
                await client.close()
                self.assertFalse(client.is_running)

        asyncio.run(_run())

    # -------------------------------------------------------------------------
    # Workstream J: Git Workflows Tests
    # -------------------------------------------------------------------------

    def _init_git_repo(self) -> None:
        """Initialize a local git repository in workspace for tests."""
        subprocess.run(["git", "init"], cwd=self.workspace_root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.workspace_root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.workspace_root, check=True)

    def test_git_branch_operations(self) -> None:
        """Verify listing, creating, and switching branches via GitBranchTool."""
        self._init_git_repo()
        self.create_file("README.md", "# Test Repo\n")
        subprocess.run(["git", "add", "README.md"], cwd=self.workspace_root, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=self.workspace_root, check=True)

        tool = GitBranchTool()

        # 1. List branches
        res = asyncio.run(tool.execute({"action": "list"}, self.context))
        self.assertTrue(res.ok)

        # 2. Create new branch
        res_create = asyncio.run(tool.execute({"action": "create", "branch": "feature-auth"}, self.context))
        self.assertTrue(res_create.ok)
        self.assertIn("feature-auth", res_create.content)

        # 3. Switch branch
        res_switch = asyncio.run(tool.execute({"action": "switch", "branch": "main"}, self.context))
        if not res_switch.ok:
            # Handle master default branch name on older git
            res_switch = asyncio.run(tool.execute({"action": "switch", "branch": "master"}, self.context))
        self.assertTrue(res_switch.ok)

    def test_git_commit_and_secret_blocking(self) -> None:
        """Verify git commit succeeds on normal files but aborts if secrets are present."""
        self._init_git_repo()
        self.create_file("src/main.py", "print('v1')\n")
        subprocess.run(["git", "add", "."], cwd=self.workspace_root, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=self.workspace_root, check=True)

        tool = GitCommitTool()

        # 1. Clean tree commit attempt should fail gracefully
        res_clean = asyncio.run(tool.execute({"message": "Empty commit"}, self.context))
        self.assertFalse(res_clean.ok)
        self.assertIn("Nothing to commit", res_clean.content)

        # 2. Normal modification commit
        self.create_file("src/main.py", "print('v2')\n")
        res_commit = asyncio.run(tool.execute({"message": "feat: update main v2"}, self.context))
        self.assertTrue(res_commit.ok)
        self.assertIn("Commit created successfully", res_commit.content)

        # 3. Secret file in working tree must block staging and commit
        self.create_file(".env", "DATABASE_KEY=secret_key\n")
        res_secret = asyncio.run(tool.execute({"message": "feat: should block"}, self.context))
        self.assertFalse(res_secret.ok)
        self.assertIn("Security block", res_secret.content)

    def test_git_log_tool(self) -> None:
        """Verify git log retrieval with bounded counts."""
        self._init_git_repo()
        self.create_file("f1.txt", "1")
        subprocess.run(["git", "add", "."], cwd=self.workspace_root, check=True)
        subprocess.run(["git", "commit", "-m", "Commit 1"], cwd=self.workspace_root, check=True)

        self.create_file("f2.txt", "2")
        subprocess.run(["git", "add", "."], cwd=self.workspace_root, check=True)
        subprocess.run(["git", "commit", "-m", "Commit 2"], cwd=self.workspace_root, check=True)

        tool = GitLogTool()
        res = asyncio.run(tool.execute({"max_count": 5}, self.context))
        self.assertTrue(res.ok)
        self.assertIn("Commit 1", res.content)
        self.assertIn("Commit 2", res.content)

    # -------------------------------------------------------------------------
    # Workstream K: Fine-Grained Permission Policies Tests
    # -------------------------------------------------------------------------

    def test_fine_grained_command_prefix_policy(self) -> None:
        """Verify declarative policy engine permits allow/deny by command prefix."""
        rules = [
            # Allow pytest test runner without interactive prompting
            PermissionRule(
                tool="terminal",
                command_prefix=["pytest"],
                decision=PolicyDecision.ALLOW,
                reason="Unit test execution auto-approved",
            ),
            # Deny dangerous recursive deletes
            PermissionRule(
                tool="terminal",
                command_prefix=["rm", "-rf"],
                decision=PolicyDecision.DENY,
                reason="Dangerous directory deletion strictly blocked",
            ),
        ]
        policy = PermissionPolicyEngine(rules=rules)
        checker = PermissionChecker(mode=PermissionMode.SUPERVISED, policy=policy)

        # 1. pytest command should be AUTO-ALLOWED (no approval needed)
        dec_test = checker.evaluate(
            PermissionLevel.EXECUTE,
            metadata={"tool": "run_command", "arguments": {"command": "pytest tests/ -v"}},
        )
        self.assertTrue(dec_test.allowed)
        self.assertFalse(dec_test.requires_approval)
        self.assertIn("auto-approved", dec_test.reason)

        # 2. rm -rf command should be DENIED
        dec_rm = checker.evaluate(
            PermissionLevel.DANGEROUS,
            metadata={"tool": "run_command", "arguments": {"command": "rm -rf /tmp/data"}},
        )
        self.assertFalse(dec_rm.allowed)
        self.assertIn("strictly blocked", dec_rm.reason)

        # 3. Unmatched command falls back to default SUPERVISED mode (requires approval)
        dec_other = checker.evaluate(
            PermissionLevel.EXECUTE,
            metadata={"tool": "run_command", "arguments": {"command": "python setup.py build"}},
        )
        self.assertTrue(dec_other.allowed)
        self.assertTrue(dec_other.requires_approval)

    def test_fine_grained_path_pattern_policy(self) -> None:
        """Verify declarative policy engine can match file paths by pattern."""
        rules = [
            PermissionRule(
                tool="create_file",
                path_pattern="*.secret",
                decision=PolicyDecision.DENY,
                reason="Secret file creation blocked by policy",
            ),
            PermissionRule(
                tool="read_file",
                path_pattern="docs/*",
                decision=PolicyDecision.ALLOW,
                reason="Documentation reading auto-approved",
            ),
        ]
        policy = PermissionPolicyEngine(rules=rules)
        checker = PermissionChecker(mode=PermissionMode.SUPERVISED, policy=policy)

        # 1. *.secret file creation blocked
        dec_sec = checker.evaluate(
            PermissionLevel.READ_WRITE,
            metadata={"tool": "create_file", "arguments": {"path": "keys/my.secret"}},
        )
        self.assertFalse(dec_sec.allowed)

        # 2. docs/* reading allowed
        dec_doc = checker.evaluate(
            PermissionLevel.READ_ONLY,
            metadata={"tool": "read_file", "arguments": {"path": "docs/architecture.md"}},
        )
        self.assertTrue(dec_doc.allowed)
        self.assertFalse(dec_doc.requires_approval)
