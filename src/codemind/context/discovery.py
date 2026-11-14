"""Workspace and project discovery engine."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codemind.context.ignore import IgnoreEngine


class ProjectSummary(BaseModel):
    workspace_root: str
    project_type: str = "generic"
    manifest_files: list[str] = Field(default_factory=list)
    has_readme: bool = False
    readme_excerpt: str = ""
    file_tree_summary: str = ""
    suggested_test_command: str | None = None


class ProjectDiscovery:
    """Discovers project structure, manifests, and file tree for prompt context."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()
        self.ignore_engine = IgnoreEngine(self.workspace_root)

    def analyze(self, max_tree_depth: int = 2) -> ProjectSummary:
        """Scan workspace and generate compact summary."""
        manifests: list[str] = []
        project_type = "generic"
        test_cmd = None

        # Check manifests
        manifest_map = {
            "pyproject.toml": ("Python", "python3 -m unittest discover -s tests"),
            "setup.py": ("Python", "python3 setup.py test"),
            "requirements.txt": ("Python", "pytest"),
            "package.json": ("Node / TypeScript", "npm test"),
            "Cargo.toml": ("Rust", "cargo test"),
            "go.mod": ("Go", "go test ./..."),
            "pom.xml": ("Java (Maven)", "mvn test"),
            "build.gradle": ("Java / Kotlin (Gradle)", "gradle test"),
            "Makefile": ("C/C++ or Make", "make test"),
        }

        for fname, (ptype, tcmd) in manifest_map.items():
            if (self.workspace_root / fname).is_file():
                manifests.append(fname)
                if project_type == "generic":
                    project_type = ptype
                    test_cmd = tcmd

        # Check for README
        has_readme = False
        readme_excerpt = ""
        for rname in ["README.md", "README.txt", "readme.md"]:
            rpath = self.workspace_root / rname
            if rpath.is_file():
                has_readme = True
                try:
                    with open(rpath, "r", encoding="utf-8", errors="ignore") as f:
                        lines = [f.readline() for _ in range(30)]
                        readme_excerpt = "".join(lines).strip()
                except Exception:
                    pass
                break

        # Generate file tree
        tree_lines = self._build_tree(max_depth=max_tree_depth)

        return ProjectSummary(
            workspace_root=str(self.workspace_root),
            project_type=project_type,
            manifest_files=manifests,
            has_readme=has_readme,
            readme_excerpt=readme_excerpt,
            file_tree_summary="\n".join(tree_lines),
            suggested_test_command=test_cmd,
        )

    def _build_tree(self, max_depth: int = 2) -> list[str]:
        """Build compact directory tree representation."""
        tree: list[str] = []
        root_parts_len = len(self.workspace_root.parts)

        for root, dirs, files in os.walk(self.workspace_root):
            rel_path = Path(root).relative_to(self.workspace_root)
            depth = len(Path(root).parts) - root_parts_len

            # Filter ignored dirs
            dirs[:] = [
                d for d in dirs
                if not self.ignore_engine.should_ignore(Path(root) / d) and not d.startswith(".")
            ]

            if depth > max_depth:
                continue

            indent = "  " * depth
            if rel_path.parts:
                tree.append(f"{indent}📁 {rel_path.name}/")

            file_indent = "  " * (depth + 1)
            for f in sorted(files):
                if not f.startswith(".") and not self.ignore_engine.should_ignore(Path(root) / f):
                    tree.append(f"{file_indent}📄 {f}")
                    if len(tree) > 80:
                        tree.append(f"{file_indent}... [tree truncated]")
                        return tree

        return tree
