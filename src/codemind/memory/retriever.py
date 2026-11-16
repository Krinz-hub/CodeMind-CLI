"""Multi-stage relevance retrieval and context budgeting engine for persistent memory."""

from __future__ import annotations

from typing import Any
from codemind.context.discovery import ProjectSummary
from codemind.memory.models import (
    MemoryEntry,
    MemoryLayer,
    MemorySearchResult,
    MemoryStatus,
)
from codemind.memory.store import SQLiteProjectMemory


class MemoryRetriever:
    """Retrieves and budgets project memory records for context injection."""

    def __init__(self, memory: SQLiteProjectMemory, max_budget_chars: int = 6000):
        self.memory = memory
        self.max_budget_chars = max_budget_chars

    def retrieve_context(
        self,
        instruction: str,
        project_summary: ProjectSummary | None = None,
    ) -> str:
        """Retrieve relevant memories across Layers A, B, C, D and format within budget."""
        sections: list[str] = []
        current_chars = 0

        # 1. Layer D: Project-Specific User Directives (Highest priority rules)
        directives = self.memory.list_entries(
            layer=MemoryLayer.INSTRUCTION,
            status=MemoryStatus.ACTIVE,
            limit=20,
        )
        if directives:
            directive_lines = ["### Workspace Guidelines & Directives (Layer D)"]
            for d in directives:
                directive_lines.append(f"- **{d.title}**: {d.content}")
            sec_text = "\n".join(directive_lines)
            sections.append(sec_text)
            current_chars += len(sec_text)

        # 2. Layer A: Baseline Project Memory (Identity, tech stack, test command)
        project_memories = self.memory.list_entries(
            layer=MemoryLayer.PROJECT,
            status=MemoryStatus.ACTIVE,
            limit=20,
        )
        # Filter project memories (prioritize pinned ones like purpose, stack, test_cmd)
        if project_memories:
            proj_lines = ["### Persistent Project Knowledge (Layer A)"]
            for pm in project_memories:
                stale_mark = " *(Warning: referenced file missing)*" if self.memory.check_stale(pm) else ""
                proj_lines.append(f"**{pm.title}**{stale_mark}:\n{pm.content.strip()}\n")
            sec_text = "\n".join(proj_lines)
            if current_chars + len(sec_text) < self.max_budget_chars:
                sections.append(sec_text)
                current_chars += len(sec_text)

        # 3. Dynamic Relevance Retrieval for Layer B (Decisions / ADRs)
        # Extract keywords and run FTS5 search
        decision_results = self.memory.search(
            query=instruction,
            layer=MemoryLayer.DECISION,
            status=MemoryStatus.ACTIVE,
            limit=5,
        )
        # Also include pinned active decisions even if search didn't catch them
        pinned_decisions = [
            d for d in self.memory.list_entries(layer=MemoryLayer.DECISION, status=MemoryStatus.ACTIVE)
            if d.pinned and not any(r.entry.id == d.id for r in decision_results)
        ]
        all_decision_entries = [r.entry for r in decision_results] + pinned_decisions

        if all_decision_entries:
            dec_lines = ["### Architectural Decisions & Rationale (Layer B)"]
            for dec in all_decision_entries:
                stale_mark = " [STALE]" if self.memory.check_stale(dec) else ""
                meta_note = ""
                if dec.metadata:
                    if "rejected_alternatives" in dec.metadata:
                        meta_note += f" | Rejected: {dec.metadata['rejected_alternatives']}"
                    if "trade_offs" in dec.metadata:
                        meta_note += f" | Trade-offs: {dec.metadata['trade_offs']}"
                line = f"- **{dec.title}**{stale_mark}: {dec.content.strip()}{meta_note}"
                if current_chars + len(line) + 20 < self.max_budget_chars:
                    dec_lines.append(line)
                    current_chars += len(line)
            if len(dec_lines) > 1:
                sections.append("\n".join(dec_lines))

        # 4. Dynamic Relevance Retrieval for Layer C (Task History & Defects)
        task_results = self.memory.search(
            query=instruction,
            layer=MemoryLayer.TASK,
            status=MemoryStatus.ACTIVE,
            limit=5,
        )
        if task_results:
            task_lines = ["### Relevant Prior Tasks & Operational History (Layer C)"]
            for tr in task_results:
                task = tr.entry
                stale_mark = " [STALE - Files moved or deleted]" if tr.is_stale else ""
                meta_info = ""
                if "files" in task.metadata and task.metadata["files"]:
                    meta_info += f" (Files touched: {', '.join(task.metadata['files'])})"
                line = f"- **{task.title}**{stale_mark}: {task.content.strip()}{meta_info}"
                if current_chars + len(line) + 20 < self.max_budget_chars:
                    task_lines.append(line)
                    current_chars += len(line)
            if len(task_lines) > 1:
                sections.append("\n".join(task_lines))

        if not sections:
            return ""

        joined_content = "\n\n".join(sections)
        if len(joined_content) > self.max_budget_chars:
            joined_content = joined_content[: self.max_budget_chars] + "\n... [Memory truncated to budget]"

        return joined_content
