"""Base definitions and contract for the CodeMind tool system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codemind.security.permissions import PermissionChecker, PermissionLevel
from codemind.security.sandbox import WorkspaceSandbox


class ToolResult(BaseModel):
    """Normalized output from all tool invocations."""

    ok: bool = True
    content: str = Field(default="", description="Human/model readable output or message")
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    error_code: str | None = None
    truncated: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def success(cls, content: str, **kwargs: Any) -> ToolResult:
        return cls(ok=True, content=content, **kwargs)

    @classmethod
    def error(cls, message: str, error_code: str = "TOOL_ERROR", **kwargs: Any) -> ToolResult:
        return cls(ok=False, content=message, error_code=error_code, **kwargs)


class ExecutionContext(BaseModel):
    """Contextual runtime environment provided to tool executors."""

    model_config = {"arbitrary_types_allowed": True}

    workspace_root: Path
    sandbox: WorkspaceSandbox
    permission_checker: PermissionChecker
    max_output_bytes: int = 65536
    timeout_seconds: int = 60
    ui: Any = None

    def truncate_output(self, text: str) -> tuple[str, bool]:
        """Enforce maximum byte limit on output strings."""
        encoded = text.encode("utf-8", errors="replace")
        if len(encoded) > self.max_output_bytes:
            truncated_bytes = encoded[: self.max_output_bytes]
            decoded = truncated_bytes.decode("utf-8", errors="ignore")
            notice = f"\n\n[... Truncated: Exceeded {self.max_output_bytes} bytes limit ...]"
            return decoded + notice, True
        return text, False


class BaseTool(ABC):
    """Abstract base class for all tools exposed to the agent."""

    name: str
    description: str
    permission_level: PermissionLevel = PermissionLevel.READ_ONLY
    timeout: int = 60
    args_schema: type[BaseModel]

    @abstractmethod
    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """Execute the tool operation."""
        pass
