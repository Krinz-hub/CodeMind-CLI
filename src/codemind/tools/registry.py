"""Central ToolRegistry managing tool definitions, permissions, and dispatch."""

from __future__ import annotations

import json
from typing import Any

from codemind.security.permissions import PermissionDecision
from codemind.security.redaction import redact_secrets
from codemind.tools.base import BaseTool, ExecutionContext, ToolResult
from codemind.tools.filesystem import CreateFileTool, ListDirectoryTool, ReadFileTool, WriteFileTool
from codemind.tools.git import GitDiffTool, GitStatusTool
from codemind.tools.patch import ApplyPatchTool
from codemind.tools.search import SearchFilesTool, SearchTextTool
from codemind.tools.terminal import RunCommandTool


class ToolRegistry:
    """Manages active tool definitions, schema generation, and secure execution."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self.register_default_tools()

    def register(self, tool: BaseTool) -> None:
        """Register a new tool instance."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def register_default_tools(self) -> None:
        """Register standard baseline tools for Phase 1-6."""
        self.register(ReadFileTool())
        self.register(ListDirectoryTool())
        self.register(CreateFileTool())
        self.register(WriteFileTool())
        self.register(ApplyPatchTool())
        self.register(SearchFilesTool())
        self.register(SearchTextTool())
        self.register(RunCommandTool())
        self.register(GitStatusTool())
        self.register(GitDiffTool())

    def get_prompt_definitions(self) -> str:
        """Generate formatted documentation of tools and their JSON schemas for the system prompt."""
        defs: list[str] = []
        for tool in self._tools.values():
            schema_json = json.dumps(tool.args_schema.model_json_schema(), indent=2)
            defs.append(
                f"Tool: {tool.name}\n"
                f"Description: {tool.description}\n"
                f"Permission Level: {tool.permission_level.value}\n"
                f"Arguments Schema:\n{schema_json}\n"
            )
        return "\n" + ("=" * 40) + "\nAVAILABLE TOOLS\n" + ("=" * 40) + "\n\n" + "\n".join(defs)

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        """Validate permissions, prompt for approval if required, and execute the tool."""
        tool = self.get(tool_name)
        if not tool:
            return ToolResult.error(f"Unknown tool '{tool_name}'.", error_code="UNKNOWN_TOOL")

        # 1. Permission check
        decision: PermissionDecision = context.permission_checker.evaluate(
            tool.permission_level,
            metadata={"tool": tool_name, "arguments": arguments},
        )
        if not decision.allowed:
            return ToolResult.error(decision.reason, error_code="PERMISSION_DENIED")

        # 2. Interactive approval gate if required
        if decision.requires_approval:
            prompt_msg = f"Approve action '{tool_name}' ({decision.reason})?"
            if context.ui and hasattr(context.ui, "request_approval"):
                approved = context.ui.request_approval(prompt_msg)
            else:
                # If no interactive UI available, default to rejecting write/execute actions
                approved = False

            if not approved:
                return ToolResult.error(
                    f"Action '{tool_name}' was rejected by user.",
                    error_code="APPROVAL_REJECTED",
                )

        # 3. Argument schema validation
        try:
            tool.args_schema.model_validate(arguments)
        except Exception as ex:
            return ToolResult.error(
                f"Invalid arguments for tool '{tool_name}': {ex}",
                error_code="SCHEMA_VALIDATION_ERROR",
            )

        # 4. Tool execution
        try:
            result = await tool.execute(arguments, context)
            # Redact any accidental secrets in result content
            result.content = redact_secrets(result.content)
            return result
        except Exception as ex:
            return ToolResult.error(f"Execution failure in tool '{tool_name}': {ex}")
