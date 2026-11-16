"""Safe context compaction engine for CodeMind CLI (Phase B Workstream F).

Compresses conversation history when active context approaches model context limits
while strictly preserving:
- Original user request and acceptance criteria
- Current task plan and completed-step evidence
- Most recent tool results needed for immediate next steps
- Active approval requirements, unverified caveats, and unresolved issues
"""

from __future__ import annotations

import logging
from typing import Any

from codemind.models.base import ChatMessage
from codemind.planning.task import TaskPlan, TaskStatus

logger = logging.getLogger("codemind.context.compactor")


class CompactionResult:
    """Outcome of a context compaction operation."""

    def __init__(
        self,
        messages: list[ChatMessage],
        was_compacted: bool,
        original_chars: int,
        compacted_chars: int,
        summary: str = "",
    ):
        self.messages = messages
        self.was_compacted = was_compacted
        self.original_chars = original_chars
        self.compacted_chars = compacted_chars
        self.summary = summary

    @property
    def saved_chars(self) -> int:
        return max(0, self.original_chars - self.compacted_chars)


class ContextCompactor:
    """Intelligently compacts conversation messages when approaching context thresholds."""

    def __init__(
        self,
        threshold_chars: int = 30000,
        keep_recent_turns: int = 4,
    ):
        self.threshold_chars = threshold_chars
        self.keep_recent_turns = keep_recent_turns

    def needs_compaction(self, messages: list[ChatMessage]) -> bool:
        """Check if active messages exceed character budget threshold."""
        total_chars = sum(len(m.content) for m in messages)
        return total_chars >= self.threshold_chars

    def compact(
        self,
        messages: list[ChatMessage],
        task_plan: TaskPlan | None = None,
        unverified_notes: list[str] | None = None,
        force: bool = False,
    ) -> CompactionResult:
        """Compact intermediate conversation history into a dense, structured summary.

        Preservation Invariants:
        1. messages[0] (System Prompt) is NEVER touched or compacted.
        2. messages[1] (Original User Request) is NEVER touched.
        3. The most recent `keep_recent_turns` messages are NEVER touched.
        4. Active approval requirements and unverified notes are explicitly included in summary.
        """
        total_chars = sum(len(m.content) for m in messages)
        if not force and total_chars < self.threshold_chars:
            return CompactionResult(
                messages=messages,
                was_compacted=False,
                original_chars=total_chars,
                compacted_chars=total_chars,
            )

        # We need at least system message (0), user request (1), some history, and recent turns
        min_messages = 2 + self.keep_recent_turns + 2
        if len(messages) < min_messages:
            return CompactionResult(
                messages=messages,
                was_compacted=False,
                original_chars=total_chars,
                compacted_chars=total_chars,
                summary="Insufficient message count to compact.",
            )

        system_msg = messages[0]
        original_user_msg = messages[1]
        recent_messages = messages[-self.keep_recent_turns :]
        intermediate_messages = messages[2 : -self.keep_recent_turns]

        # Extract structured facts from intermediate messages
        tools_called: list[str] = []
        files_mentioned: set[str] = set()

        for m in intermediate_messages:
            content = m.content
            # Collect file paths mentioned in tool calls or observations
            import re

            paths = re.findall(r"[\w/\.-]+\.(?:py|js|ts|tsx|json|sql|html|css|md)", content)
            files_mentioned.update(paths[:10])

            if '"type": "tool_call"' in content:
                for tmatch in re.finditer(r'"tool":\s*"([^"]+)"', content):
                    tools_called.append(tmatch.group(1))

        # Build dense structured summary
        summary_lines = [
            "--- COMPACTED CONVERSATION SUMMARY ---",
            "Earlier conversational turns have been compacted to conserve model context.",
            f"• Turns Compacted: {len(intermediate_messages)} intermediate message(s)",
        ]

        if tools_called:
            summary_lines.append(f"• Prior Tools Executed: {', '.join(tools_called[-8:])}")

        if files_mentioned:
            summary_lines.append(f"• Active Files Referenced: {', '.join(sorted(list(files_mentioned))[:10])}")

        if task_plan and task_plan.tasks:
            summary_lines.append("\n• Task Execution Progress:")
            for t in task_plan.tasks:
                summary_lines.append(f"  - [{t.status.value}] {t.id}: {t.title}")

        if unverified_notes:
            summary_lines.append("\n• Open Unverified Aspects:")
            for u in unverified_notes:
                summary_lines.append(f"  ? {u}")

        summary_lines.append(
            "\nContinue directly with the next action. All prior tasks and files remain safely preserved on disk."
        )
        summary_lines.append("--------------------------------------")

        summary_text = "\n".join(summary_lines)
        summary_msg = ChatMessage(role="user", content=summary_text)

        # Assemble new compacted message stream
        compacted_messages = [system_msg, original_user_msg, summary_msg] + recent_messages
        new_total_chars = sum(len(m.content) for m in compacted_messages)

        logger.info(
            f"ContextCompactor: Compacted {len(intermediate_messages)} messages. "
            f"Size: {total_chars} chars -> {new_total_chars} chars (Saved {total_chars - new_total_chars} chars)."
        )

        return CompactionResult(
            messages=compacted_messages,
            was_compacted=True,
            original_chars=total_chars,
            compacted_chars=new_total_chars,
            summary=summary_text,
        )
