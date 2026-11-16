"""File mentions processor (@file) for CodeMind CLI (Phase C Workstream H).

Parses @file mentions in user prompts, canonicalizes paths, enforces sandbox boundaries,
blocks secret files, and injects bounded file context to save discovery turns.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codemind.context.ignore import IgnoreEngine
from codemind.security.sandbox import WorkspaceSandbox

# Matches @path/to/file or @.env preceded by start-of-line or whitespace
MENTION_REGEX = re.compile(r"(?:^|(?<=\s))@([a-zA-Z0-9_\./-]*[a-zA-Z0-9_-])(?=[,\.!\?:;\s]|$)")

MAX_MENTION_BYTES = 10240  # 10 KB per mentioned file
MAX_MENTION_LINES = 200


class MentionedFileContext(BaseModel):
    rel_path: str
    content: str
    line_count: int
    truncated: bool = False
    warning: str | None = None


class FileMentionProcessor:
    """Discovers, validates, and safely injects file context from @file mentions."""

    def __init__(self, workspace_root: Path, sandbox: WorkspaceSandbox | None = None):
        self.workspace_root = workspace_root.resolve()
        self.sandbox = sandbox or WorkspaceSandbox(self.workspace_root)
        self.ignore_engine = IgnoreEngine(self.workspace_root)

    def extract_mentions(self, text: str) -> list[str]:
        """Extract distinct file paths prefixed with @ from text."""
        raw_matches = MENTION_REGEX.findall(text)
        distinct: list[str] = []
        for m in raw_matches:
            cleaned = m.strip()
            if cleaned and cleaned not in distinct:
                distinct.append(cleaned)
        return distinct

    def process_mentions(self, text: str) -> tuple[str, list[MentionedFileContext]]:
        """Process all @mentions in text, validating boundaries and reading bounded content."""
        mention_paths = self.extract_mentions(text)
        contexts: list[MentionedFileContext] = []

        for rel_str in mention_paths:
            # Strip leading @ or slash if present
            clean_rel = rel_str.lstrip("@/").strip()
            target_path = (self.workspace_root / clean_rel).resolve()

            # 1. Enforce sandbox containment
            if not self.sandbox.is_within_workspace(target_path):
                contexts.append(
                    MentionedFileContext(
                        rel_path=clean_rel,
                        content="",
                        line_count=0,
                        warning=f"Access blocked: '{clean_rel}' is outside the authorized workspace.",
                    )
                )
                continue

            # 2. Block secret and credential files
            if self.sandbox.is_secret_file(target_path):
                contexts.append(
                    MentionedFileContext(
                        rel_path=clean_rel,
                        content="",
                        line_count=0,
                        warning=f"Security violation: Access to secret file '{clean_rel}' is blocked.",
                    )
                )
                continue

            # 3. Check file existence
            if not target_path.is_file():
                contexts.append(
                    MentionedFileContext(
                        rel_path=clean_rel,
                        content="",
                        line_count=0,
                        warning=f"File not found: '{clean_rel}' does not exist on disk.",
                    )
                )
                continue

            # 4. Check ignore rules
            rel_to_ws = target_path.relative_to(self.workspace_root)
            if self.ignore_engine.should_ignore(rel_to_ws):
                contexts.append(
                    MentionedFileContext(
                        rel_path=clean_rel,
                        content="",
                        line_count=0,
                        warning=f"File '{clean_rel}' matches ignore rules and was omitted.",
                    )
                )
                continue

            # 5. Read bounded content safely
            try:
                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                    lines: list[str] = []
                    byte_count = 0
                    truncated = False
                    for idx, line in enumerate(f, start=1):
                        byte_count += len(line.encode("utf-8"))
                        if idx > MAX_MENTION_LINES or byte_count > MAX_MENTION_BYTES:
                            truncated = True
                            break
                        lines.append(line)

                    content = "".join(lines)
                    contexts.append(
                        MentionedFileContext(
                            rel_path=str(rel_to_ws),
                            content=content,
                            line_count=len(lines),
                            truncated=truncated,
                        )
                    )
            except Exception as ex:
                contexts.append(
                    MentionedFileContext(
                        rel_path=clean_rel,
                        content="",
                        line_count=0,
                        warning=f"Could not read file: {ex}",
                    )
                )

        # Build augmented prompt text
        augmented_prompt = text
        if contexts:
            injected_sections: list[str] = ["\n\n--- INJECTED CONTEXT (FILE MENTIONS) ---"]
            for ctx in contexts:
                if ctx.warning:
                    injected_sections.append(f"[@{ctx.rel_path}]: {ctx.warning}")
                else:
                    trunc_str = " (truncated to budget)" if ctx.truncated else ""
                    injected_sections.append(
                        f"[@{ctx.rel_path} ({ctx.line_count} lines){trunc_str}]:\n```\n{ctx.content.strip()}\n```"
                    )
            injected_sections.append("------------------------------------------")
            augmented_prompt += "\n".join(injected_sections)

        return augmented_prompt, contexts
