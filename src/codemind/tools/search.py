"""File and text searching tools."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codemind.security.permissions import PermissionLevel
from codemind.security.sandbox import SecurityViolationError
from codemind.tools.base import BaseTool, ExecutionContext, ToolResult


# --- search_files ---
class SearchFilesInput(BaseModel):
    pattern: str = Field(description="Glob pattern to search for (e.g. '*.py', '*test*')")
    path: str = Field(default=".", description="Subdirectory to search inside (default '.')")


class SearchFilesTool(BaseTool):
    name = "search_files"
    description = "Search for files by name matching a glob pattern inside the workspace."
    permission_level = PermissionLevel.READ_ONLY
    args_schema = SearchFilesInput

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            inp = SearchFilesInput.model_validate(arguments)
            target = context.sandbox.validate_path_access(inp.path, is_write=False)
            if not target.is_dir():
                return ToolResult.error(f"Directory not found: '{inp.path}'")

            matches: list[str] = []
            for root, dirs, files in os.walk(target):
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith(".") and d not in ["__pycache__", "node_modules", "target", "venv", ".git"]
                ]
                for file_name in files:
                    if fnmatch.fnmatch(file_name, inp.pattern):
                        full_path = Path(root) / file_name
                        if not context.sandbox.is_secret_file(full_path):
                            rel = full_path.relative_to(context.workspace_root)
                            matches.append(str(rel))

            if not matches:
                return ToolResult.success(f"No files matching pattern '{inp.pattern}' found in '{inp.path}'.")

            matches.sort()
            content = f"Found {len(matches)} matching file(s):\n" + "\n".join(matches[:200])
            truncated, is_trunc = context.truncate_output(content)
            return ToolResult.success(truncated, truncated=is_trunc, metadata={"count": len(matches)})
        except SecurityViolationError as sec_err:
            return ToolResult.error(str(sec_err), error_code="SECURITY_VIOLATION")
        except Exception as ex:
            return ToolResult.error(f"Error searching files: {ex}")


# --- search_text ---
class SearchTextInput(BaseModel):
    query: str = Field(description="Text substring or token to search for")
    path: str = Field(default=".", description="Directory path to search in (default '.')")
    file_pattern: str = Field(default="*", description="Optional glob filter for filenames (e.g. '*.py')")
    max_matches: int = Field(default=50, description="Maximum number of match occurrences to return")


class SearchTextTool(BaseTool):
    name = "search_text"
    description = "Search for text or tokens across workspace files (grep-like)."
    permission_level = PermissionLevel.READ_ONLY
    args_schema = SearchTextInput

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            inp = SearchTextInput.model_validate(arguments)
            target = context.sandbox.validate_path_access(inp.path, is_write=False)
            if not target.is_dir():
                return ToolResult.error(f"Directory not found: '{inp.path}'")

            results: list[str] = []
            total_found = 0

            for root, dirs, files in os.walk(target):
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith(".") and d not in ["__pycache__", "node_modules", "target", "venv", ".git"]
                ]
                for file_name in files:
                    if not fnmatch.fnmatch(file_name, inp.file_pattern):
                        continue

                    full_path = Path(root) / file_name
                    if context.sandbox.is_secret_file(full_path):
                        continue

                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            rel = full_path.relative_to(context.workspace_root)
                            for line_idx, line in enumerate(f, start=1):
                                if inp.query in line:
                                    results.append(f"{rel}:{line_idx}: {line.strip()}")
                                    total_found += 1
                                    if total_found >= inp.max_matches:
                                        break
                    except Exception:
                        continue

                    if total_found >= inp.max_matches:
                        break
                if total_found >= inp.max_matches:
                    break

            if not results:
                return ToolResult.success(f"No occurrences of '{inp.query}' found.")

            content = f"Found {len(results)} matches for '{inp.query}':\n" + "\n".join(results)
            truncated, is_trunc = context.truncate_output(content)
            return ToolResult.success(truncated, truncated=is_trunc, metadata={"count": len(results)})
        except SecurityViolationError as sec_err:
            return ToolResult.error(str(sec_err), error_code="SECURITY_VIOLATION")
        except Exception as ex:
            return ToolResult.error(f"Error searching text: {ex}")
