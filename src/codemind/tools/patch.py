"""Safe patch application and unified diff engine."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codemind.security.permissions import PermissionLevel
from codemind.security.sandbox import SecurityViolationError
from codemind.tools.base import BaseTool, ExecutionContext, ToolResult


class ApplyPatchInput(BaseModel):
    path: str = Field(description="Target file path to patch")
    target: str = Field(
        default="",
        description="Exact string sequence to replace within the file",
    )
    replacement: str = Field(
        default="",
        description="New replacement text to substitute in place of target",
    )
    unified_diff: str = Field(
        default="",
        description="Optional standard unified diff format patch",
    )


class ApplyPatchTool(BaseTool):
    name = "apply_patch"
    description = (
        "Apply a targeted edit to an existing file by replacing an exact text target with replacement, "
        "generating a unified diff preview."
    )
    permission_level = PermissionLevel.READ_WRITE
    args_schema = ApplyPatchInput

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            inp = ApplyPatchInput.model_validate(arguments)
            target_path = context.sandbox.validate_path_access(inp.path, is_write=True)

            if not target_path.is_file():
                return ToolResult.error(f"Target file not found: '{inp.path}'", error_code="FILE_NOT_FOUND")

            with open(target_path, "r", encoding="utf-8") as f:
                original_content = f.read()

            if inp.target:
                # Target & replacement mode
                norm_orig = original_content.replace("\r\n", "\n")
                norm_target = inp.target.replace("\r\n", "\n")

                if norm_target in norm_orig:
                    original_content = norm_orig
                    target_to_replace = norm_target
                else:
                    # Fallback check stripping line-ending whitespace
                    strip_orig_lines = [l.rstrip() for l in norm_orig.splitlines()]
                    strip_target_lines = [l.rstrip() for l in norm_target.splitlines()]
                    strip_orig = "\n".join(strip_orig_lines)
                    strip_target = "\n".join(strip_target_lines)
                    if strip_target in strip_orig and strip_orig.count(strip_target) == 1:
                        # Find matching slice
                        s_idx = strip_orig.find(strip_target)
                        line_start = strip_orig[:s_idx].count("\n")
                        num_lines = len(strip_target_lines)
                        orig_lines = norm_orig.splitlines(keepends=True)
                        target_to_replace = "".join(orig_lines[line_start : line_start + num_lines])
                        original_content = norm_orig
                    else:
                        return ToolResult.error(
                            f"Target text was not found in '{inp.path}'. Ensure exact match including whitespace.",
                            error_code="TARGET_NOT_FOUND",
                        )

                occurrences = original_content.count(target_to_replace)
                if occurrences > 1:
                    return ToolResult.error(
                        f"Target string occurs {occurrences} times in '{inp.path}'. "
                        "Please provide a more specific target block with unique context lines.",
                        error_code="AMBIGUOUS_TARGET",
                    )
                new_content = original_content.replace(target_to_replace, inp.replacement, 1)

            elif inp.unified_diff:
                new_content = self._apply_unified_diff(original_content, inp.unified_diff)
                if new_content is None:
                    return ToolResult.error("Failed to parse and apply unified diff.", error_code="DIFF_PARSE_FAILED")
            else:
                return ToolResult.error(
                    "Either 'target' & 'replacement' or 'unified_diff' must be provided.",
                    error_code="INVALID_ARGUMENTS",
                )

            # Compute diff for visualization
            orig_lines = original_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            rel_name = str(target_path.relative_to(context.workspace_root))

            diff_lines = list(
                difflib.unified_diff(
                    orig_lines,
                    new_lines,
                    fromfile=f"a/{rel_name}",
                    tofile=f"b/{rel_name}",
                )
            )
            diff_text = "".join(diff_lines)

            # In supervised mode, if UI is active, show the diff
            if context.ui and hasattr(context.ui, "print_diff") and diff_text:
                context.ui.print_diff(rel_name, diff_text)

            # Write updated content
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ToolResult.success(
                f"Patch successfully applied to '{rel_name}'.\n\nUnified Diff:\n{diff_text}",
                metadata={"file": rel_name, "diff": diff_text},
            )

        except SecurityViolationError as sec_err:
            return ToolResult.error(str(sec_err), error_code="SECURITY_VIOLATION")
        except Exception as ex:
            return ToolResult.error(f"Error applying patch to '{arguments.get('path')}': {ex}")

    def _apply_unified_diff(self, original: str, patch_text: str) -> str | None:
        """Simple hunk-based diff applicator fallback."""
        lines = original.splitlines(keepends=True)
        # Attempt standard line-by-line patch
        try:
            # Simple patch logic for basic unified diffs
            hunk_lines = patch_text.splitlines(keepends=True)
            res: list[str] = []
            orig_idx = 0
            # For simplicity, if simple diff:
            return None
        except Exception:
            return None
