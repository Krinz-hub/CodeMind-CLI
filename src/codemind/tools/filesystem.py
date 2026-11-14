"""Filesystem inspection and modification tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codemind.security.permissions import PermissionLevel
from codemind.security.sandbox import SecurityViolationError
from codemind.tools.base import BaseTool, ExecutionContext, ToolResult


# --- read_file ---
class ReadFileInput(BaseModel):
    path: str = Field(description="Relative or absolute path to the file to read")
    offset: int = Field(default=1, description="Line number to begin reading from (1-indexed)")
    limit: int = Field(default=250, description="Maximum number of lines to read")


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read lines from a file within the workspace, including line numbers."
    permission_level = PermissionLevel.READ_ONLY
    args_schema = ReadFileInput

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            inp = ReadFileInput.model_validate(arguments)
            target = context.sandbox.validate_path_access(inp.path, is_write=False)
            if not target.is_file():
                return ToolResult.error(f"File not found: '{inp.path}'", error_code="FILE_NOT_FOUND")

            with open(target, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            start_idx = max(0, inp.offset - 1)
            end_idx = min(total_lines, start_idx + inp.limit)
            selected = lines[start_idx:end_idx]

            output_lines = [
                f"{i + 1:4d} | {line.rstrip()}"
                for i, line in enumerate(selected, start=start_idx)
            ]
            header = f"[File: {target.relative_to(context.workspace_root)} ({total_lines} total lines, showing {start_idx+1}-{end_idx})]\n"
            full_text = header + "\n".join(output_lines)

            truncated_text, is_trunc = context.truncate_output(full_text)
            return ToolResult.success(truncated_text, truncated=is_trunc, metadata={"lines": total_lines})
        except SecurityViolationError as sec_err:
            return ToolResult.error(str(sec_err), error_code="SECURITY_VIOLATION")
        except Exception as ex:
            return ToolResult.error(f"Error reading file '{arguments.get('path')}': {ex}")


# --- list_directory ---
class ListDirectoryInput(BaseModel):
    path: str = Field(default=".", description="Relative directory path to inspect")
    max_depth: int = Field(default=2, description="Maximum traversal depth (default 2)")


class ListDirectoryTool(BaseTool):
    name = "list_directory"
    description = "List files and subdirectories in a directory path respecting ignore filters."
    permission_level = PermissionLevel.READ_ONLY
    args_schema = ListDirectoryInput

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            inp = ListDirectoryInput.model_validate(arguments)
            target = context.sandbox.validate_path_access(inp.path, is_write=False)
            if not target.is_dir():
                return ToolResult.error(f"Directory not found: '{inp.path}'", error_code="DIR_NOT_FOUND")

            entries: list[str] = []
            target_depth = len(target.parts)

            for root, dirs, files in os.walk(target):
                current_depth = len(Path(root).parts) - target_depth
                # Filter out hidden or cache directories
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith(".") and d not in ["__pycache__", "node_modules", "target", "venv", ".git"]
                ]
                if current_depth > inp.max_depth:
                    continue

                rel_root = Path(root).relative_to(context.workspace_root)
                for d in dirs:
                    entries.append(f"dir : {rel_root / d}/")
                for f in files:
                    if not f.startswith("."):
                        entries.append(f"file: {rel_root / f}")

            if not entries:
                return ToolResult.success(f"Directory '{inp.path}' is empty or contains only ignored entries.")

            content = f"[Directory Listing for '{inp.path}']\n" + "\n".join(sorted(entries[:500]))
            truncated_text, is_trunc = context.truncate_output(content)
            return ToolResult.success(truncated_text, truncated=is_trunc)
        except SecurityViolationError as sec_err:
            return ToolResult.error(str(sec_err), error_code="SECURITY_VIOLATION")
        except Exception as ex:
            return ToolResult.error(f"Error listing directory '{arguments.get('path')}': {ex}")


# --- create_file ---
class CreateFileInput(BaseModel):
    path: str = Field(description="Path of the new file to create")
    content: str = Field(description="Text content to write into the file")


class CreateFileTool(BaseTool):
    name = "create_file"
    description = "Create a new file within the workspace with specified text content."
    permission_level = PermissionLevel.READ_WRITE
    args_schema = CreateFileInput

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            inp = CreateFileInput.model_validate(arguments)
            target = context.sandbox.validate_path_access(inp.path, is_write=True)
            if target.exists():
                return ToolResult.error(
                    f"File already exists: '{inp.path}'. Use apply_patch or write_file instead.",
                    error_code="FILE_EXISTS",
                )

            # Ensure parent directories exist
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(inp.content)

            return ToolResult.success(
                f"Successfully created '{target.relative_to(context.workspace_root)}' ({len(inp.content)} bytes).",
                metadata={"path": str(target), "bytes": len(inp.content)},
            )
        except SecurityViolationError as sec_err:
            return ToolResult.error(str(sec_err), error_code="SECURITY_VIOLATION")
        except Exception as ex:
            return ToolResult.error(f"Error creating file '{arguments.get('path')}': {ex}")


# --- write_file ---
class WriteFileInput(BaseModel):
    path: str = Field(description="Path of file to write or overwrite")
    content: str = Field(description="Content to write")


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write or overwrite a file within the workspace (requires approval)."
    permission_level = PermissionLevel.READ_WRITE
    args_schema = WriteFileInput

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            inp = WriteFileInput.model_validate(arguments)
            target = context.sandbox.validate_path_access(inp.path, is_write=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(inp.content)

            return ToolResult.success(
                f"Successfully wrote {len(inp.content)} bytes to '{target.relative_to(context.workspace_root)}'.",
                metadata={"path": str(target), "bytes": len(inp.content)},
            )
        except SecurityViolationError as sec_err:
            return ToolResult.error(str(sec_err), error_code="SECURITY_VIOLATION")
        except Exception as ex:
            return ToolResult.error(f"Error writing file '{arguments.get('path')}': {ex}")
