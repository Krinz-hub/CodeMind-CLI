"""Skill loader and matching engine for .codemind/skills/."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SkillDefinition(BaseModel):
    name: str
    description: str = ""
    triggers: list[str] = Field(default_factory=list)
    instructions: str = ""
    path: str = ""


class SkillLoader:
    """Discovers and loads SKILL.md definitions."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.skills_dir = self.workspace_root / ".codemind" / "skills"

    def load_all_skills(self) -> list[SkillDefinition]:
        """Scan .codemind/skills/*/SKILL.md files."""
        skills: list[SkillDefinition] = []
        if not self.skills_dir.is_dir():
            return skills

        for skill_file in self.skills_dir.glob("*/SKILL.md"):
            try:
                skill = self._parse_skill_file(skill_file)
                if skill:
                    skills.append(skill)
            except Exception:
                continue

        return skills

    def find_applicable_skills(self, manifest_files: list[str], prompt: str) -> list[SkillDefinition]:
        """Select skills relevant to the current project and prompt."""
        all_skills = self.load_all_skills()
        applicable: list[SkillDefinition] = []

        prompt_lower = prompt.lower()
        for skill in all_skills:
            # Check prompt mentions
            if skill.name.lower() in prompt_lower:
                applicable.append(skill)
                continue

            # Check trigger matches against manifests
            matched_trigger = False
            for trigger in skill.triggers:
                for manifest in manifest_files:
                    if fnmatch.fnmatch(manifest, trigger):
                        applicable.append(skill)
                        matched_trigger = True
                        break
                if matched_trigger:
                    break

        return applicable

    def _parse_skill_file(self, path: Path) -> SkillDefinition | None:
        """Parse frontmatter and markdown body of a SKILL.md file."""
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        name = path.parent.name
        description = ""
        triggers: list[str] = []
        instructions = content

        # Check for YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                instructions = parts[2].strip()
                for line in frontmatter.splitlines():
                    line = line.strip()
                    if line.startswith("name:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("description:"):
                        description = line.split(":", 1)[1].strip()
                    elif line.startswith("-") and "triggers" in frontmatter:
                        triggers.append(line.lstrip("-").strip().strip('"').strip("'"))

        return SkillDefinition(
            name=name,
            description=description,
            triggers=triggers,
            instructions=instructions,
            path=str(path),
        )
