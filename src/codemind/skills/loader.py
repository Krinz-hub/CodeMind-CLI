"""Backward-compatible skill loader interface backed by SkillRegistry."""

from __future__ import annotations

from pathlib import Path
from codemind.skills.models import SkillDefinition
from codemind.skills.registry import SkillRegistry


class SkillLoader:
    """Discovers and loads SKILL.md definitions, delegating to the unified SkillRegistry."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.registry = SkillRegistry(self.workspace_root)

    def load_all_skills(self) -> list[SkillDefinition]:
        """Scan all skills across built-in, user, and project tiers."""
        return self.registry.discover_all()

    def find_applicable_skills(self, manifest_files: list[str], prompt: str) -> list[SkillDefinition]:
        """Select skills relevant to the current project and prompt."""
        res = self.registry.select_skills(
            instruction=prompt,
            manifest_files=manifest_files,
        )
        return res.selected_skills
