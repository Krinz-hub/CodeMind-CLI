"""Context budgeting and prompt assembly engine."""

from __future__ import annotations

from typing import Any

from codemind.context.discovery import ProjectSummary


class ContextBudget:
    """Allocates character / token budgets across different prompt components."""

    def __init__(self, max_context_chars: int = 40000):
        self.max_context_chars = max_context_chars

    def assemble_system_prompt(
        self,
        base_instructions: str,
        tool_definitions: str,
        project_summary: ProjectSummary | None = None,
        active_plan_text: str | None = None,
        skills_text: str | None = None,
        memory_text: str | None = None,
    ) -> str:
        """Compose bounded structured system prompt."""
        sections = [base_instructions]

        if project_summary:
            proj_sec = (
                f"\n--- PROJECT CONTEXT ---\n"
                f"Workspace Root: {project_summary.workspace_root}\n"
                f"Project Type: {project_summary.project_type}\n"
                f"Manifests: {', '.join(project_summary.manifest_files) or 'None'}\n"
            )
            if project_summary.suggested_test_command:
                proj_sec += f"Detected Test Command: {project_summary.suggested_test_command}\n"
            if project_summary.has_readme and project_summary.readme_excerpt:
                proj_sec += f"\nREADME Excerpt:\n{project_summary.readme_excerpt[:1500]}\n"
            if project_summary.file_tree_summary:
                proj_sec += f"\nFile Structure:\n{project_summary.file_tree_summary}\n"
            sections.append(proj_sec)

        if memory_text:
            sections.append(f"\n--- PERSISTENT PROJECT MEMORY ---\n{memory_text.strip()}\n")

        if active_plan_text:
            sections.append(f"\n--- ACTIVE TASK PLAN ---\n{active_plan_text}\n")

        if skills_text:
            sections.append(f"\n--- PROJECT SKILLS & GUIDELINES ---\n{skills_text}\n")

        sections.append(tool_definitions)

        # Append protocol requirements
        protocol_instructions = (
            "\n--- RESPONSE PROTOCOL (VERSION 1) ---\n"
            "You MUST respond using a single JSON envelope matching protocol_version '1'.\n"
            "Do not include commentary or markdown outside the JSON.\n\n"
            "Examples:\n"
            "1. Tool Call:\n"
            '{"protocol_version": "1", "type": "tool_call", "tool": "read_file", "arguments": {"path": "src/main.py"}, "reason": "Inspect router"}\n\n'
            "2. Plan Update:\n"
            '{"protocol_version": "1", "type": "plan", "plan": [{"id": "t1", "title": "Inspect code", "status": "completed"}], "reason": "Updated plan"}\n\n'
            "3. Final Response:\n"
            '{"protocol_version": "1", "type": "final", "content": "Detailed explanation or task completion message.", "summary": ["Action 1", "Action 2"]}\n'
        )
        sections.append(protocol_instructions)

        full_prompt = "\n".join(sections)
        if len(full_prompt) > self.max_context_chars:
            # Simple truncation guard
            full_prompt = full_prompt[: self.max_context_chars] + "\n... [Context truncated to budget]"

        return full_prompt
