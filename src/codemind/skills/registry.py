"""Dynamic skills registry, hierarchical discovery, selection, and lifecycle management."""

from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

from codemind.skills.models import (
    SkillDefinition,
    SkillManifest,
    SkillSelectionResult,
    SkillTrigger,
    SkillValidationIssue,
)

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent / "builtin"


class SkillRegistry:
    """Discovers, validates, filters, and manages versioned CodeMind engineering skills."""

    def __init__(self, workspace_root: Path, user_skills_dir: Path | None = None):
        self.workspace_root = workspace_root.resolve()
        self.project_skills_dir = self.workspace_root / ".codemind" / "skills"
        self.user_skills_dir = user_skills_dir or (Path.home() / ".codemind" / "skills")
        self.builtin_skills_dir = BUILTIN_SKILLS_DIR
        self.config_file = self.workspace_root / ".codemind" / "skills_config.json"
        self._skills_cache: dict[str, SkillDefinition] | None = None
        self._validation_issues: list[SkillValidationIssue] = []

    def _load_config(self) -> dict[str, Any]:
        """Load project-specific skill enablement configuration."""
        if self.config_file.is_file():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_config(self, config: dict[str, Any]) -> None:
        """Save project-specific skill enablement configuration."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    def parse_skill_file(self, path: Path, source: str) -> tuple[SkillDefinition | None, list[SkillValidationIssue]]:
        """Parse and validate a SKILL.md file with YAML frontmatter."""
        issues: list[SkillValidationIssue] = []
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            issues.append(SkillValidationIssue(skill_path=str(path), severity="error", message=f"Cannot read file: {e}"))
            return None, issues

        if not content.startswith("---"):
            # Fallback parsing for legacy simple markdown files
            name = path.parent.name
            manifest = SkillManifest(
                name=name,
                version="1.0.0",
                description=f"Legacy skill {name}",
                category="general",
                triggers=SkillTrigger(keywords=[name]),
            )
            return SkillDefinition(manifest=manifest, instructions=content.strip(), path=str(path), source=source), issues

        parts = content.split("---", 2)
        if len(parts) < 3:
            issues.append(SkillValidationIssue(skill_path=str(path), severity="error", message="Malformed frontmatter: missing closing '---' delimiter."))
            return None, issues

        frontmatter_raw = parts[1].strip()
        instructions = parts[2].strip()

        try:
            parsed_yaml = yaml.safe_load(frontmatter_raw)
            if not isinstance(parsed_yaml, dict):
                issues.append(SkillValidationIssue(skill_path=str(path), severity="error", message="Frontmatter must be a YAML dictionary mapping."))
                return None, issues
        except Exception as ye:
            issues.append(SkillValidationIssue(skill_path=str(path), severity="error", message=f"YAML syntax error: {ye}"))
            return None, issues

        # Normalize triggers
        triggers_data = parsed_yaml.get("triggers", {})
        if isinstance(triggers_data, list):
            # Legacy triggers list format
            manifest_triggers = SkillTrigger(keywords=[str(t) for t in triggers_data])
        elif isinstance(triggers_data, dict):
            manifest_triggers = SkillTrigger(
                manifests=[str(m) for m in triggers_data.get("manifests", [])],
                globs=[str(g) for g in triggers_data.get("globs", [])],
                keywords=[str(k) for k in triggers_data.get("keywords", [])],
            )
        else:
            manifest_triggers = SkillTrigger()

        name = str(parsed_yaml.get("name", path.parent.name))

        try:
            manifest = SkillManifest(
                name=name,
                version=str(parsed_yaml.get("version", "1.0.0")),
                description=str(parsed_yaml.get("description", "")),
                category=str(parsed_yaml.get("category", "general")),
                triggers=manifest_triggers,
                required_tools=[str(t) for t in parsed_yaml.get("required_tools", [])],
                dependencies=[str(d) for d in parsed_yaml.get("dependencies", [])],
                conflicts=[str(c) for c in parsed_yaml.get("conflicts", [])],
                workflow_steps=[str(s) for s in parsed_yaml.get("workflow_steps", [])],
                constraints=[str(c) for c in parsed_yaml.get("constraints", [])],
                verification=[str(v) for v in parsed_yaml.get("verification", [])],
                enabled=bool(parsed_yaml.get("enabled", True)),
            )
        except Exception as ve:
            issues.append(SkillValidationIssue(skill_path=str(path), severity="error", message=f"Manifest schema validation error: {ve}"))
            return None, issues

        return SkillDefinition(manifest=manifest, instructions=instructions, path=str(path), source=source), issues

    def discover_all(self, refresh: bool = False) -> list[SkillDefinition]:
        """Discover skills across Builtin, User, and Project tiers with precedence override."""
        if self._skills_cache is not None and not refresh:
            return list(self._skills_cache.values())

        skills_by_name: dict[str, SkillDefinition] = {}
        self._validation_issues = []
        cfg = self._load_config()
        disabled_set = set(cfg.get("disabled_skills", []))
        enabled_set = set(cfg.get("enabled_skills", []))

        # 1. Built-in Skills (Lowest precedence)
        if self.builtin_skills_dir.is_dir():
            for skill_file in sorted(self.builtin_skills_dir.glob("*/SKILL.md")):
                skill, issues = self.parse_skill_file(skill_file, source="builtin")
                self._validation_issues.extend(issues)
                if skill:
                    skills_by_name[skill.name] = skill

        # 2. User-level Skills (Medium precedence)
        if self.user_skills_dir.is_dir():
            for skill_file in sorted(self.user_skills_dir.glob("*/SKILL.md")):
                skill, issues = self.parse_skill_file(skill_file, source="user")
                self._validation_issues.extend(issues)
                if skill:
                    skills_by_name[skill.name] = skill

        # 3. Project-level Skills (Highest precedence, overrides user & builtin)
        if self.project_skills_dir.is_dir():
            for skill_file in sorted(self.project_skills_dir.glob("*/SKILL.md")):
                skill, issues = self.parse_skill_file(skill_file, source="project")
                self._validation_issues.extend(issues)
                if skill:
                    skills_by_name[skill.name] = skill

        # Apply configuration enablement toggles
        for name, skill in skills_by_name.items():
            if name in disabled_set:
                skill.manifest.enabled = False
            elif name in enabled_set:
                skill.manifest.enabled = True

        self._skills_cache = skills_by_name
        return list(skills_by_name.values())

    def get_skill(self, name: str) -> SkillDefinition | None:
        """Retrieve a specific skill by name."""
        all_skills = self.discover_all()
        clean = name.strip().lower()
        for s in all_skills:
            if s.name == clean:
                return s
        return None

    def search_skills(self, query: str) -> list[SkillDefinition]:
        """Search skills across name, description, category, and keywords."""
        all_skills = self.discover_all()
        q = query.strip().lower()
        if not q:
            return all_skills

        matches = []
        for s in all_skills:
            if (
                q in s.name
                or q in s.description.lower()
                or q in s.category.lower()
                or any(q in kw.lower() for kw in s.manifest.triggers.keywords)
            ):
                matches.append(s)
        return matches

    def validate_all(self) -> list[SkillValidationIssue]:
        """Scan and validate all skill files, returning all discovered issues."""
        self.discover_all(refresh=True)
        return list(self._validation_issues)

    def set_skill_enabled(self, name: str, enabled: bool) -> bool:
        """Enable or disable a specific skill in project configuration."""
        skill = self.get_skill(name)
        if not skill:
            return False

        cfg = self._load_config()
        disabled = set(cfg.get("disabled_skills", []))
        enabled_set = set(cfg.get("enabled_skills", []))

        clean = name.strip().lower()
        if enabled:
            disabled.discard(clean)
            enabled_set.add(clean)
        else:
            disabled.add(clean)
            enabled_set.discard(clean)

        cfg["disabled_skills"] = sorted(list(disabled))
        cfg["enabled_skills"] = sorted(list(enabled_set))
        self._save_config(cfg)
        self.discover_all(refresh=True)
        return True

    def select_skills(
        self,
        instruction: str,
        manifest_files: list[str] | None = None,
        project_type: str = "",
        memory_context: str = "",
        max_candidates: int = 4,
    ) -> SkillSelectionResult:
        """Execute 2-stage intelligent selection: pre-filtering, dependency resolution, and conflict management."""
        all_skills = [s for s in self.discover_all() if s.enabled]
        manifests = manifest_files or []
        inst_lower = instruction.lower()
        mem_lower = memory_context.lower()

        # Stage 1: Scoring and Candidate Pre-Filtering
        candidate_scores: list[tuple[SkillDefinition, float, list[str]]] = []

        for skill in all_skills:
            score = 0.0
            reasons = []

            # 1. Exact or keyword name mention in prompt
            if skill.name in inst_lower or skill.name.replace("-", " ") in inst_lower:
                score += 5.0
                reasons.append(f"Skill name '{skill.name}' matched prompt")

            # 2. Manifest matching
            matched_manifests = []
            for trigger_m in skill.manifest.triggers.manifests:
                for actual_m in manifests:
                    if fnmatch.fnmatch(actual_m, trigger_m):
                        matched_manifests.append(actual_m)
            if matched_manifests:
                score += 3.0
                reasons.append(f"Matched manifest(s): {', '.join(matched_manifests)}")

            # 3. Intent keyword matching
            matched_keywords = []
            for kw in skill.manifest.triggers.keywords:
                kw_clean = kw.lower()
                pattern = r"\b" + re.escape(kw_clean) + (r"s?\b" if not kw_clean.endswith("s") else r"\b")
                if re.search(pattern, inst_lower):
                    matched_keywords.append(kw)
            if matched_keywords:
                score += 2.0 * len(matched_keywords)
                reasons.append(f"Matched intent keyword(s): {', '.join(matched_keywords)}")

            # 4. Project type & Memory grounding
            if project_type and skill.category.lower() in project_type.lower():
                score += 1.5
                reasons.append(f"Matched project type '{project_type}'")
            if skill.name in mem_lower:
                score += 2.0
                reasons.append("Referenced in project memory")

            if score > 0.0:
                candidate_scores.append((skill, score, reasons))

        # Sort candidates by score descending
        candidate_scores.sort(key=lambda x: x[1], reverse=True)
        top_candidates = [item[0] for item in candidate_scores[:max_candidates]]

        if not top_candidates:
            return SkillSelectionResult(
                selected_skills=[],
                candidate_skills=[],
                rationale="No relevant skills matched the task instruction or project configuration.",
            )

        # Stage 2: Selection, Dependency Resolution & Conflict Handling
        selected_dict: dict[str, SkillDefinition] = {}
        deps_resolved: list[str] = []
        conflicts_suppressed: list[str] = []
        rationale_lines: list[str] = []

        for skill, score, reasons in candidate_scores[:max_candidates]:
            selected_dict[skill.name] = skill
            rationale_lines.append(f"- Selected '{skill.name}' (Score: {score:.1f}): {'; '.join(reasons)}")

        # Resolve dependencies
        for skill_name, skill in list(selected_dict.items()):
            for dep_name in skill.dependencies:
                if dep_name not in selected_dict:
                    dep_skill = self.get_skill(dep_name)
                    if dep_skill and dep_skill.enabled:
                        selected_dict[dep_name] = dep_skill
                        deps_resolved.append(f"Auto-resolved prerequisite '{dep_name}' for '{skill_name}'")
                        rationale_lines.append(f"- Auto-loaded prerequisite '{dep_name}' required by '{skill_name}'")

        # Handle conflicts cleanly with precedence and score comparison
        for skill_name in list(selected_dict.keys()):
            if skill_name not in selected_dict:
                continue
            skill = selected_dict[skill_name]
            for conflict_name in skill.conflicts:
                if conflict_name in selected_dict and conflict_name != skill_name:
                    conflicting_skill = selected_dict[conflict_name]
                    score_skill = next((s[1] for s in candidate_scores if s[0].name == skill.name), 0.0)
                    score_conflict = next((s[1] for s in candidate_scores if s[0].name == conflict_name), 0.0)

                    if skill.source == "project" and conflicting_skill.source != "project":
                        del selected_dict[conflict_name]
                        conflicts_suppressed.append(f"Suppressed '{conflict_name}' in favor of project-level '{skill.name}'")
                    elif conflicting_skill.source == "project" and skill.source != "project":
                        del selected_dict[skill_name]
                        conflicts_suppressed.append(f"Suppressed '{skill.name}' in favor of project-level '{conflict_name}'")
                        break
                    elif score_skill >= score_conflict:
                        del selected_dict[conflict_name]
                        conflicts_suppressed.append(f"Suppressed '{conflict_name}' due to conflict with higher-ranked '{skill.name}'")
                    else:
                        del selected_dict[skill_name]
                        conflicts_suppressed.append(f"Suppressed '{skill.name}' due to conflict with higher-ranked '{conflict_name}'")
                        break

        selected_list = list(selected_dict.values())
        return SkillSelectionResult(
            selected_skills=selected_list,
            candidate_skills=top_candidates,
            rationale="\n".join(rationale_lines),
            dependencies_resolved=deps_resolved,
            conflicts_suppressed=conflicts_suppressed,
        )

    def format_skills_for_prompt(self, skills: list[SkillDefinition], max_chars: int = 5000) -> str:
        """Format active skill procedures and constraints within a strict context budget."""
        if not skills:
            return ""

        sections: list[str] = []
        current_chars = 0

        for skill in skills:
            lines = [f"### Skill: {skill.name} (v{skill.version} - {skill.category})"]
            lines.append(f"**Description:** {skill.description}")

            if skill.workflow_steps:
                lines.append("\n**Procedural Workflow Steps:**")
                for step in skill.workflow_steps:
                    lines.append(f"- {step}")

            if skill.constraints:
                lines.append("\n**Authoritative Constraints:**")
                for c in skill.constraints:
                    lines.append(f"- {c}")

            if skill.verification:
                lines.append("\n**Verification Protocol:**")
                for v in skill.verification:
                    lines.append(f"- {v}")

            # Append concise instruction excerpt if budget allows
            if skill.instructions and len(skill.instructions) < 1500:
                clean_body = re.sub(r"^#+ .*", "", skill.instructions, flags=re.MULTILINE).strip()
                if clean_body:
                    lines.append(f"\n**Execution Guidance:**\n{clean_body[:800]}")

            sec_text = "\n".join(lines)
            if current_chars + len(sec_text) + 20 < max_chars:
                sections.append(sec_text)
                current_chars += len(sec_text)
            else:
                # Add compact version if budget constrained
                compact = f"### Skill: {skill.name}\n" + "\n".join(skill.workflow_steps[:3])
                if current_chars + len(compact) < max_chars:
                    sections.append(compact)
                    current_chars += len(compact)
                break

        return "\n\n".join(sections)
