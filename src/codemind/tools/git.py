"""Read-only Git inspection tools."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from codemind.security.permissions import PermissionLevel
from codemind.tools.base import BaseTool, ExecutionContext, ToolResult


class GitStatusInput(BaseModel):
    pass


class GitStatusTool(BaseTool):
    name = "git_status"
    description = "Inspect git working tree status (untracked, modified, staged files)."
    permission_level = PermissionLevel.READ_ONLY
    args_schema = GitStatusInput

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "status",
                "--short",
                cwd=str(context.workspace_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err_msg = stderr.decode("utf-8", errors="replace").strip()
                return ToolResult.error(f"Git error: {err_msg}", error_code="GIT_ERROR")

            status_text = stdout.decode("utf-8", errors="replace").strip()
            if not status_text:
                return ToolResult.success("Working tree clean. No modified or untracked files.")

            return ToolResult.success(f"Git Status:\n{status_text}")
        except FileNotFoundError:
            return ToolResult.error("git binary not found on system PATH.", error_code="GIT_NOT_FOUND")
        except Exception as ex:
            return ToolResult.error(f"Error checking git status: {ex}")


class GitDiffInput(BaseModel):
    staged: bool = Field(default=False, description="If true, show staged changes (git diff --cached)")
    path: str | None = Field(default=None, description="Optional path to scope the diff to")


class GitDiffTool(BaseTool):
    name = "git_diff"
    description = "View unified diff of uncommitted changes in the repository."
    permission_level = PermissionLevel.READ_ONLY
    args_schema = GitDiffInput

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            inp = GitDiffInput.model_validate(arguments)
            cmd = ["git", "diff"]
            if inp.staged:
                cmd.append("--cached")
            if inp.path:
                target = context.sandbox.validate_path_access(inp.path, is_write=False)
                cmd.append(str(target.relative_to(context.workspace_root)))

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(context.workspace_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err_msg = stderr.decode("utf-8", errors="replace").strip()
                return ToolResult.error(f"Git diff error: {err_msg}", error_code="GIT_ERROR")

            diff_text = stdout.decode("utf-8", errors="replace").strip()
            if not diff_text:
                return ToolResult.success("No diff found.")

            truncated, is_trunc = context.truncate_output(diff_text)
            return ToolResult.success(truncated, truncated=is_trunc)
        except Exception as ex:
            return ToolResult.error(f"Error checking git diff: {ex}")
