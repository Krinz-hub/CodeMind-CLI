"""Git inspection and workflow manipulation tools (Phase D Workstream J)."""

from __future__ import annotations

import asyncio
from pathlib import Path
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


class GitBranchInput(BaseModel):
    action: str = Field(default="list", description="Action: 'list', 'create', or 'switch'")
    branch: str | None = Field(default=None, description="Target branch name for 'create' or 'switch'")


class GitBranchTool(BaseTool):
    name = "git_branch"
    description = "Inspect, create, or switch Git branches."
    permission_level = PermissionLevel.READ_WRITE
    args_schema = GitBranchInput

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            inp = GitBranchInput.model_validate(arguments)
            action = inp.action.lower()

            if action == "list":
                proc = await asyncio.create_subprocess_exec(
                    "git", "branch", "--list",
                    cwd=str(context.workspace_root),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    return ToolResult.error(f"Git error: {stderr.decode('utf-8').strip()}")
                return ToolResult.success(stdout.decode("utf-8").strip() or "No branches found.")

            if action == "create":
                if not inp.branch:
                    return ToolResult.error("Must specify 'branch' name to create a branch.")
                proc = await asyncio.create_subprocess_exec(
                    "git", "checkout", "-b", inp.branch,
                    cwd=str(context.workspace_root),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    return ToolResult.error(f"Git error: {stderr.decode('utf-8').strip()}")
                return ToolResult.success(f"Created and switched to new branch '{inp.branch}'.")

            if action == "switch":
                if not inp.branch:
                    return ToolResult.error("Must specify 'branch' name to switch branches.")
                proc = await asyncio.create_subprocess_exec(
                    "git", "checkout", inp.branch,
                    cwd=str(context.workspace_root),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    return ToolResult.error(f"Git error: {stderr.decode('utf-8').strip()}")
                return ToolResult.success(f"Switched to branch '{inp.branch}'.")

            return ToolResult.error(f"Unknown action '{inp.action}'. Supported: 'list', 'create', 'switch'.")
        except Exception as ex:
            return ToolResult.error(f"Error executing git branch: {ex}")


class GitCommitInput(BaseModel):
    message: str = Field(description="Commit message following conventional commit guidelines")
    files: list[str] | None = Field(default=None, description="Optional list of files to stage; if omitted, stages all non-secret changes")


class GitCommitTool(BaseTool):
    name = "git_commit"
    description = "Stage modified files and create an approved Git commit."
    permission_level = PermissionLevel.READ_WRITE
    args_schema = GitCommitInput

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            inp = GitCommitInput.model_validate(arguments)
            if not inp.message.strip():
                return ToolResult.error("Commit message cannot be empty.")

            # Check status first
            proc = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                cwd=str(context.workspace_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                return ToolResult.error(f"Git error: {stderr.decode('utf-8').strip()}")

            status_lines = stdout.decode("utf-8").strip().splitlines()
            if not status_lines:
                return ToolResult.error("Working tree is clean. Nothing to commit.")

            # Stage files safely
            if inp.files:
                for f in inp.files:
                    target = context.sandbox.validate_path_access(f, is_write=False)
                    if context.sandbox.is_secret_file(target):
                        return ToolResult.error(f"Security block: Cannot commit secret file '{f}'.")
                    add_proc = await asyncio.create_subprocess_exec(
                        "git", "add", str(target.relative_to(context.workspace_root)),
                        cwd=str(context.workspace_root),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await add_proc.communicate()
            else:
                # Add all tracked and untracked, but verify secrets aren't staged
                for line in status_lines:
                    fname = line[3:].strip()
                    full_p = context.workspace_root / fname
                    if context.sandbox.is_secret_file(full_p):
                        return ToolResult.error(f"Security block: Found secret file '{fname}' in working tree. Staging aborted.")

                add_proc = await asyncio.create_subprocess_exec(
                    "git", "add", "-A",
                    cwd=str(context.workspace_root),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await add_proc.communicate()

            # Execute commit
            commit_proc = await asyncio.create_subprocess_exec(
                "git", "commit", "-m", inp.message.strip(),
                cwd=str(context.workspace_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out_c, err_c = await commit_proc.communicate()
            if commit_proc.returncode != 0:
                return ToolResult.error(f"Git commit failed: {err_c.decode('utf-8').strip()}")

            commit_output = out_c.decode("utf-8").strip()
            return ToolResult.success(f"Commit created successfully:\n{commit_output}")

        except Exception as ex:
            return ToolResult.error(f"Error creating git commit: {ex}")


class GitLogInput(BaseModel):
    max_count: int = Field(default=10, description="Maximum number of commits to retrieve")


class GitLogTool(BaseTool):
    name = "git_log"
    description = "Inspect recent commit history in the repository."
    permission_level = PermissionLevel.READ_ONLY
    args_schema = GitLogInput

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            inp = GitLogInput.model_validate(arguments)
            proc = await asyncio.create_subprocess_exec(
                "git", "log", f"-n{inp.max_count}", "--oneline",
                cwd=str(context.workspace_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                return ToolResult.error(f"Git log error: {stderr.decode('utf-8').strip()}")

            log_text = stdout.decode("utf-8").strip()
            if not log_text:
                return ToolResult.success("No commits found.")
            return ToolResult.success(log_text)
        except Exception as ex:
            return ToolResult.error(f"Error checking git log: {ex}")
