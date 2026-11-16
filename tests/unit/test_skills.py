"""Unit tests for the dynamic skills discovery, selection, and execution engine."""

import json
from pathlib import Path

from typer.testing import CliRunner

from codemind.cli.main import app
from codemind.skills.models import SkillManifest, SkillTrigger
from codemind.skills.registry import SkillRegistry
from tests.base import BaseAgentTestCase


class TestSkills(BaseAgentTestCase):
    """Test suite for SkillRegistry, manifest validation, discovery precedence, and selection."""

    def setUp(self) -> None:
        super().setUp()
        self.runner = CliRunner()
        self.registry = SkillRegistry(self.workspace_root)

    def test_builtin_skills_discovery(self) -> None:
        """Verify all 10 core built-in skills are discovered with valid schemas."""
        skills = self.registry.discover_all()
        skill_names = {s.name for s in skills if s.source == "builtin"}

        expected_builtin = {
            "python-backend",
            "react-frontend",
            "react-native-expo",
            "api-development",
            "database-engineering",
            "debugging",
            "testing",
            "ui-ux-design",
            "git-workflow",
            "codebase-understanding",
        }
        self.assertTrue(expected_builtin.issubset(skill_names))
        self.assertEqual(len(self.registry.validate_all()), 0)

    def test_hierarchical_precedence(self) -> None:
        """Verify project-level skills override user-level and built-in skills."""
        # Create a custom project-level override for 'testing'
        project_skill_dir = self.workspace_root / ".codemind" / "skills" / "testing"
        project_skill_dir.mkdir(parents=True, exist_ok=True)
        (project_skill_dir / "SKILL.md").write_text(
            """---
name: testing
version: 2.0.0
description: Project-specific testing overrides with strict pytest enforcement.
category: testing
triggers:
  keywords:
    - test
workflow_steps:
  - "1. Run pytest only."
---
# Custom Testing Protocol
"""
        )

        fresh_registry = SkillRegistry(self.workspace_root)
        testing_skill = fresh_registry.get_skill("testing")

        self.assertIsNotNone(testing_skill)
        assert testing_skill is not None
        self.assertEqual(testing_skill.source, "project")
        self.assertEqual(testing_skill.version, "2.0.0")
        self.assertIn("pytest enforcement", testing_skill.description)

    def test_manifest_validation_diagnostics(self) -> None:
        """Verify malformed or invalid skills are flagged with diagnostic issues."""
        # Malformed name (uppercase and spaces)
        bad_dir = self.workspace_root / ".codemind" / "skills" / "bad-skill"
        bad_dir.mkdir(parents=True, exist_ok=True)
        (bad_dir / "SKILL.md").write_text(
            """---
name: BAD SKILL NAME
version: 1.0.0
---
Bad skill body
"""
        )

        fresh_registry = SkillRegistry(self.workspace_root)
        issues = fresh_registry.validate_all()

        self.assertGreater(len(issues), 0)
        self.assertTrue(any("kebab-case" in i.message for i in issues))

    def test_enable_disable_lifecycle(self) -> None:
        """Verify skills can be explicitly disabled and re-enabled."""
        skill_name = "git-workflow"
        self.assertTrue(self.registry.get_skill(skill_name).enabled)

        # Disable
        ok = self.registry.set_skill_enabled(skill_name, enabled=False)
        self.assertTrue(ok)
        self.assertFalse(self.registry.get_skill(skill_name).enabled)

        # Confirm persisted in config
        cfg_file = self.workspace_root / ".codemind" / "skills_config.json"
        self.assertTrue(cfg_file.is_file())
        with open(cfg_file, "r") as f:
            cfg = json.load(f)
        self.assertIn(skill_name, cfg.get("disabled_skills", []))

        # Re-enable
        ok = self.registry.set_skill_enabled(skill_name, enabled=True)
        self.assertTrue(ok)
        self.assertTrue(self.registry.get_skill(skill_name).enabled)

    def test_intelligent_selection_python(self) -> None:
        """Verify intelligent selection matches python-backend for python service tasks."""
        res = self.registry.select_skills(
            instruction="Create a FastAPI authentication service with type annotations",
            manifest_files=["pyproject.toml"],
            project_type="Python",
        )
        selected_names = [s.name for s in res.selected_skills]
        self.assertIn("python-backend", selected_names)
        self.assertIn("api-development", selected_names)
        self.assertNotIn("react-frontend", selected_names)

    def test_intelligent_selection_react(self) -> None:
        """Verify intelligent selection matches react-frontend for React component tasks."""
        res = self.registry.select_skills(
            instruction="Build a responsive UserProfile card component with hooks",
            manifest_files=["package.json"],
            project_type="React",
        )
        selected_names = [s.name for s in res.selected_skills]
        self.assertIn("react-frontend", selected_names)
        self.assertNotIn("python-backend", selected_names)

    def test_null_skill_matching(self) -> None:
        """Verify generic tasks without relevant engineering skills return empty without hallucination."""
        res = self.registry.select_skills(
            instruction="What is the current date and time?",
            manifest_files=[],
        )
        self.assertEqual(len(res.selected_skills), 0)
        self.assertIn("No relevant skills matched", res.rationale)

    def test_dependency_resolution(self) -> None:
        """Verify dependent skills are automatically loaded when a parent skill is selected."""
        # react-native-expo declares dependency on react-frontend
        res = self.registry.select_skills(
            instruction="Build an Expo mobile navigation screen",
            manifest_files=["app.json"],
        )
        selected_names = [s.name for s in res.selected_skills]
        self.assertIn("react-native-expo", selected_names)
        self.assertIn("react-frontend", selected_names)
        self.assertTrue(any("Auto-resolved prerequisite 'react-frontend'" in d for d in res.dependencies_resolved))

    def test_conflict_suppression(self) -> None:
        """Verify conflicting skills are cleanly suppressed with project precedence."""
        # Create a conflicting project-level skill
        vue_dir = self.workspace_root / ".codemind" / "skills" / "vue-frontend"
        vue_dir.mkdir(parents=True, exist_ok=True)
        (vue_dir / "SKILL.md").write_text(
            """---
name: vue-frontend
version: 1.0.0
description: Vue 3 single file components.
category: frontend
conflicts:
  - react-frontend
triggers:
  keywords:
    - component
---
Vue steps
"""
        )

        fresh_reg = SkillRegistry(self.workspace_root)
        # Query with package.json
        res = fresh_reg.select_skills(
            instruction="Create a component with React hooks",
            manifest_files=["package.json"],
        )
        selected_names = [s.name for s in res.selected_skills]
        # Project-level vue-frontend suppresses conflicting builtin react-frontend
        self.assertIn("vue-frontend", selected_names)
        self.assertNotIn("react-frontend", selected_names)
        self.assertTrue(any("Suppressed 'react-frontend' in favor of project-level 'vue-frontend'" in c for c in res.conflicts_suppressed))

    def test_prompt_context_budget_enforcement(self) -> None:
        """Verify format_skills_for_prompt adheres to strict character boundaries."""
        all_skills = self.registry.discover_all()[:3]
        formatted = self.registry.format_skills_for_prompt(all_skills, max_chars=1200)

        self.assertLessEqual(len(formatted), 1200)
        self.assertIn("### Skill:", formatted)

    def test_skills_cli_suite(self) -> None:
        """Verify skills CLI subcommands execute properly."""
        ws = str(self.workspace_root)

        # 1. list
        r = self.runner.invoke(app, ["skills", "list", "--plain", "-w", ws])
        self.assertEqual(r.exit_code, 0)
        self.assertIn("python-backend", r.output)

        # 2. show
        r = self.runner.invoke(app, ["skills", "show", "python-backend", "--plain", "-w", ws])
        self.assertEqual(r.exit_code, 0)
        self.assertIn("Procedural Workflow Steps:", r.output)

        # 3. search
        r = self.runner.invoke(app, ["skills", "search", "fastapi", "--plain", "-w", ws])
        self.assertEqual(r.exit_code, 0)
        self.assertIn("python-backend", r.output)

        # 4. inspect
        r = self.runner.invoke(app, ["skills", "inspect", "api-development", "--plain", "-w", ws])
        self.assertEqual(r.exit_code, 0)
        self.assertIn("Required Tools:", r.output)

        # 5. validate
        r = self.runner.invoke(app, ["skills", "validate", "--plain", "-w", ws])
        self.assertEqual(r.exit_code, 0)
        self.assertIn("Validation successful", r.output)

        # 6. disable
        r = self.runner.invoke(app, ["skills", "disable", "debugging", "--plain", "-w", ws])
        self.assertEqual(r.exit_code, 0)
        self.assertIn("DISABLED", r.output)

        # 7. enable
        r = self.runner.invoke(app, ["skills", "enable", "debugging", "--plain", "-w", ws])
        self.assertEqual(r.exit_code, 0)
        self.assertIn("ENABLED", r.output)
