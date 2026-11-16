"""Data models and manifest schemas for the CodeMind dynamic skills engine."""

from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel, Field, field_validator

NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?$")


class SkillTrigger(BaseModel):
    """Declarative activation triggers for a skill."""

    manifests: list[str] = Field(default_factory=list, description="Project manifests (e.g. pyproject.toml, package.json)")
    globs: list[str] = Field(default_factory=list, description="File extension globs (e.g. *.py, *.tsx, schema.prisma)")
    keywords: list[str] = Field(default_factory=list, description="Intent keywords (e.g. fastapi, component, debug, migration)")


class SkillManifest(BaseModel):
    """Structured frontmatter manifest for a versioned skill."""

    name: str = Field(description="Unique kebab-case skill identifier")
    version: str = Field(default="1.0.0", description="SemVer version string")
    description: str = Field(default="", description="Concise summary of capability")
    category: str = Field(default="general", description="Categorization (backend, frontend, database, etc.)")
    triggers: SkillTrigger = Field(default_factory=SkillTrigger, description="Activation criteria")
    required_tools: list[str] = Field(default_factory=list, description="Tools expected by this workflow")
    dependencies: list[str] = Field(default_factory=list, description="Names of prerequisite skills")
    conflicts: list[str] = Field(default_factory=list, description="Names of incompatible skills")
    workflow_steps: list[str] = Field(default_factory=list, description="Phased procedure steps")
    constraints: list[str] = Field(default_factory=list, description="Explicit boundaries and rules")
    verification: list[str] = Field(default_factory=list, description="Verification requirements")
    enabled: bool = Field(default=True, description="Whether skill is actively available")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean = v.strip().lower()
        if not NAME_PATTERN.match(clean):
            raise ValueError(f"Skill name '{v}' must be lowercase alphanumeric with hyphens (kebab-case).")
        return clean

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        clean = v.strip()
        if not SEMVER_PATTERN.match(clean):
            raise ValueError(f"Skill version '{v}' must adhere to SemVer (X.Y.Z).")
        return clean


class SkillDefinition(BaseModel):
    """In-memory representation of a validated skill."""

    manifest: SkillManifest
    instructions: str = Field(default="", description="Full markdown instruction body")
    path: str = Field(default="", description="Filesystem path to SKILL.md")
    source: str = Field(default="builtin", description="Origin tier: 'builtin', 'user', or 'project'")

    # --- Backward compatibility convenience accessors ---
    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def description(self) -> str:
        return self.manifest.description

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def category(self) -> str:
        return self.manifest.category

    @property
    def triggers(self) -> list[str]:
        # Legacy property returning flat list of all trigger strings
        return self.manifest.triggers.manifests + self.manifest.triggers.globs + self.manifest.triggers.keywords

    @property
    def required_tools(self) -> list[str]:
        return self.manifest.required_tools

    @property
    def dependencies(self) -> list[str]:
        return self.manifest.dependencies

    @property
    def conflicts(self) -> list[str]:
        return self.manifest.conflicts

    @property
    def workflow_steps(self) -> list[str]:
        return self.manifest.workflow_steps

    @property
    def constraints(self) -> list[str]:
        return self.manifest.constraints

    @property
    def verification(self) -> list[str]:
        return self.manifest.verification

    @property
    def enabled(self) -> bool:
        return self.manifest.enabled


class SkillSelectionResult(BaseModel):
    """Output of the 2-stage intelligent skill selection process."""

    selected_skills: list[SkillDefinition] = Field(default_factory=list)
    candidate_skills: list[SkillDefinition] = Field(default_factory=list)
    rationale: str = Field(default="", description="Structured reasoning for selection")
    dependencies_resolved: list[str] = Field(default_factory=list)
    conflicts_suppressed: list[str] = Field(default_factory=list)


class SkillValidationIssue(BaseModel):
    """Diagnostic reporting for invalid or malformed skill files."""

    skill_path: str
    severity: str = "error"  # 'error' or 'warning'
    message: str
