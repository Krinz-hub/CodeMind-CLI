"""Unit tests for context discovery, ignore rules, and prompt budgeting."""

from codemind.context.budget import ContextBudget
from codemind.context.discovery import ProjectDiscovery
from codemind.context.ignore import IgnoreEngine
from tests.base import BaseAgentTestCase


class TestContext(BaseAgentTestCase):
    def test_ignore_engine(self) -> None:
        self.create_file(".gitignore", "*.log\ntmp/\n")
        engine = IgnoreEngine(self.workspace_root)

        self.assertTrue(engine.should_ignore("error.log"))
        self.assertTrue(engine.should_ignore("node_modules/package.json"))
        self.assertTrue(engine.should_ignore("__pycache__/main.cpython-312.pyc"))
        self.assertFalse(engine.should_ignore("src/main.py"))

    def test_project_discovery(self) -> None:
        self.create_file("pyproject.toml", "[project]\nname = 'demo'\n")
        self.create_file("README.md", "# Demo Project\nThis is a sample project for testing.\n")
        self.create_file("src/main.py", "print('hello')\n")

        discovery = ProjectDiscovery(self.workspace_root)
        summary = discovery.analyze()

        self.assertEqual(summary.project_type, "Python")
        self.assertIn("pyproject.toml", summary.manifest_files)
        self.assertTrue(summary.has_readme)
        self.assertIn("Demo Project", summary.readme_excerpt)

    def test_context_budget_assembly(self) -> None:
        budget = ContextBudget(max_context_chars=5000)
        prompt = budget.assemble_system_prompt(
            base_instructions="System instructions here.",
            tool_definitions="Tool: read_file",
        )
        self.assertIn("System instructions here.", prompt)
        self.assertIn("Tool: read_file", prompt)
        self.assertIn("RESPONSE PROTOCOL (VERSION 1)", prompt)
