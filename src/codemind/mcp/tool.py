"""Proxy wrapper exposing MCP server tools as native CodeMind BaseTool instances."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel

from codemind.mcp.client import MCPClient, MCPClientError
from codemind.mcp.models import MCPToolDefinition
from codemind.security.permissions import PermissionLevel
from codemind.security.redaction import redact_secrets
from codemind.tools.base import BaseTool, ExecutionContext, ToolResult


def make_mcp_args_schema(tool_name: str, input_schema: dict[str, Any]) -> type[BaseModel]:
    """Dynamically generate a Pydantic schema model matching MCP tool inputSchema."""

    class DynamicMCPArgs(BaseModel):
        model_config = {"extra": "allow"}

        @classmethod
        def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return input_schema or {"type": "object", "properties": {}}

        @classmethod
        def model_validate(cls, obj: Any, *args: Any, **kwargs: Any) -> Any:
            if isinstance(obj, dict) and input_schema:
                required = input_schema.get("required", [])
                missing = [r for r in required if r not in obj]
                if missing:
                    raise ValueError(
                        f"Missing required argument(s) for MCP tool '{tool_name}': {', '.join(missing)}"
                    )
            return super().model_validate(obj, *args, **kwargs)

    DynamicMCPArgs.__name__ = f"MCP_{tool_name.replace('-', '_')}_Args"
    return DynamicMCPArgs


class MCPProxyTool(BaseTool):
    """Bridges an external MCP server tool into CodeMind's ToolRegistry."""

    def __init__(
        self,
        server_name: str,
        tool_def: MCPToolDefinition,
        client: MCPClient,
        permission_level: PermissionLevel = PermissionLevel.EXECUTE,
    ):
        self.server_name = server_name
        self.original_tool_name = tool_def.name
        self.client = client

        # Namespace tool name to avoid collisions with internal tools
        self.name = f"mcp__{server_name}__{tool_def.name}"
        clean_desc = redact_secrets(tool_def.description or tool_def.name)
        self.description = f"[MCP: {server_name}] {clean_desc}"
        self.permission_level = permission_level
        self.args_schema = make_mcp_args_schema(self.name, tool_def.inputSchema)

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """Forward invocation to the remote MCP server via JSON-RPC."""
        try:
            res = await self.client.call_tool(
                self.original_tool_name,
                arguments,
                timeout=context.timeout_seconds,
            )

            is_error = res.get("isError", False)
            content_items = res.get("content", [])
            text_chunks: list[str] = []

            for item in content_items:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_chunks.append(item.get("text", ""))
                    elif "text" in item:
                        text_chunks.append(str(item["text"]))
                    else:
                        text_chunks.append(str(item))
                else:
                    text_chunks.append(str(item))

            joined_text = "\n".join(text_chunks).strip()
            # Treat returned content as untrusted data: scrub secrets
            joined_text = redact_secrets(joined_text)

            if not joined_text and is_error:
                joined_text = "MCP tool reported an error without descriptive text."
            elif not joined_text:
                joined_text = "Tool completed successfully with empty output."

            if is_error:
                return ToolResult.error(joined_text, error_code="MCP_TOOL_ERROR")

            truncated_text, is_trunc = context.truncate_output(joined_text)
            return ToolResult.success(truncated_text, truncated=is_trunc)

        except MCPClientError as ex:
            return ToolResult.error(f"MCP server error: {ex}", error_code="MCP_CLIENT_ERROR")
        except Exception as ex:
            return ToolResult.error(f"Unexpected error executing MCP tool: {ex}", error_code="MCP_EXECUTION_ERROR")
