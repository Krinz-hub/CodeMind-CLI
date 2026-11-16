"""Automatic post-task memory distillation engine."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from codemind.context.discovery import ProjectSummary
from codemind.memory.models import (
    MemoryEntry,
    MemoryLayer,
    MemoryStatus,
)
from codemind.memory.store import SQLiteProjectMemory
from codemind.verification.reporter import HonestCompletionReport

if TYPE_CHECKING:
    from codemind.runtime.state import AgentState

# Regex patterns indicating persistent project-level directives vs ephemeral task instructions
DIRECTIVE_PATTERNS = [
    re.compile(r"^(?:always|never|from now on|remember to|workspace rule:?|project rule:?)\s+(.+)", re.IGNORECASE),
    re.compile(r"^(?:prefer|require)\s+([a-zA-Z0-9_\-\s]+)\s+(?:over|instead of)\s+(.+)", re.IGNORECASE),
]


class MemoryDistiller:
    """Analyzes completed agent tasks and selectively distills persistent project memories."""

    def __init__(self, memory: SQLiteProjectMemory):
        self.memory = memory

    def distill(
        self,
        state: AgentState,
        report: HonestCompletionReport,
        project_summary: ProjectSummary | None = None,
    ) -> list[MemoryEntry]:
        """Extract durable accomplishments, decisions, and instructions into memory."""
        distilled: list[MemoryEntry] = []
        now_str = datetime.now(timezone.utc).isoformat()
        raw_files = sorted(list(set(state.files_created + state.files_modified)))
        all_files: list[str] = []
        for f in raw_files:
            try:
                p = Path(f)
                if p.is_absolute() and p.is_relative_to(self.memory.workspace_root):
                    all_files.append(str(p.relative_to(self.memory.workspace_root)))
                else:
                    all_files.append(f)
            except Exception:
                all_files.append(f)

        # 1. Distill Task Memory (Layer C) if meaningful work was attempted
        if all_files:
            task_uid = uuid.uuid4().hex[:8]
            inst_lower = state.task_instruction.lower()
            is_bugfix = any(w in inst_lower for w in ["fix", "bug", "repair", "defect", "patch", "error", "failing"])

            if report.verified:
                category = "bugfix" if is_bugfix else "feature"
                summary_text = "; ".join(state.final_summary) if state.final_summary else state.task_instruction
                check_details = ""
                if report.checks:
                    passed_checks = [c.command for c in report.checks if c.passed]
                    if passed_checks:
                        check_details = f" Verified by passing: {', '.join(passed_checks)}."

                entry = MemoryEntry(
                    id=f"mem_task_{task_uid}",
                    layer=MemoryLayer.TASK,
                    category=category,
                    title=f"Completed {category.capitalize()}: {state.task_instruction[:80]}",
                    content=f"{summary_text}.{check_details}",
                    metadata={
                        "files": all_files,
                        "verified": True,
                        "category": category,
                        "turn_count": state.turn_count,
                    },
                    source="agent_distillation",
                    status=MemoryStatus.ACTIVE,
                    created_at=now_str,
                    updated_at=now_str,
                )
                self.memory.add_entry(entry)
                distilled.append(entry)
            else:
                # Changes were made but verification failed or is incomplete
                unverified_msg = "; ".join(report.unverified_notes) if report.unverified_notes else "Verification did not pass."
                entry = MemoryEntry(
                    id=f"mem_task_{task_uid}",
                    layer=MemoryLayer.TASK,
                    category="unresolved_issue",
                    title=f"Unresolved Task: {state.task_instruction[:80]}",
                    content=f"Modified files ({', '.join(all_files)}) but could not verify completion. {unverified_msg}",
                    metadata={
                        "files": all_files,
                        "verified": False,
                        "category": "unresolved_issue",
                        "turn_count": state.turn_count,
                    },
                    source="agent_distillation",
                    status=MemoryStatus.ACTIVE,
                    created_at=now_str,
                    updated_at=now_str,
                )
                self.memory.add_entry(entry)
                distilled.append(entry)

        # 2. Check for explicit user directives in the instruction (Layer D)
        directive_entry = self._extract_user_directive(state.task_instruction, now_str)
        if directive_entry:
            self.memory.add_entry(directive_entry)
            distilled.append(directive_entry)

        # 3. Update Project Memory (Layer A) if manifests or test configs changed
        manifest_names = {"pyproject.toml", "package.json", "setup.py", "Cargo.toml", "go.mod", "pom.xml"}
        touched_manifests = [f for f in all_files if any(f.endswith(m) for m in manifest_names)]
        if touched_manifests and project_summary:
            # Refresh project stack memory
            self.memory.rebuild_from_project(project_summary)

        return distilled

    def _extract_user_directive(self, instruction: str, timestamp: str) -> MemoryEntry | None:
        """Filter out transient task instructions and detect persistent workspace directives."""
        inst_clean = instruction.strip()
        for pat in DIRECTIVE_PATTERNS:
            m = pat.match(inst_clean)
            if m:
                directive_uid = uuid.uuid4().hex[:8]
                return MemoryEntry(
                    id=f"mem_inst_{directive_uid}",
                    layer=MemoryLayer.INSTRUCTION,
                    category="user_directive",
                    title=f"Directive: {inst_clean[:60]}",
                    content=inst_clean,
                    source="user_instruction",
                    status=MemoryStatus.ACTIVE,
                    created_at=timestamp,
                    updated_at=timestamp,
                    pinned=True,
                )
        return None
