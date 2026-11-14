"""Ignore rule matcher supporting .gitignore and .codemindignore patterns."""

from __future__ import annotations

import fnmatch
from pathlib import Path

DEFAULT_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "bower_components",
    ".venv",
    "venv",
    "env",
    "target",
    "dist",
    "build",
    ".idea",
    ".vscode",
}

DEFAULT_IGNORED_EXTS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".bin",
    ".o",
    ".a",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".7z",
    ".iso",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".pdf",
    ".mp4",
    ".mp3",
    ".wav",
}


class IgnoreEngine:
    """Evaluates whether paths should be filtered from context and directory scans."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.patterns: list[str] = []
        self._load_ignore_files()

    def _load_ignore_files(self) -> None:
        """Load patterns from .gitignore and .codemindignore."""
        for filename in [".gitignore", ".codemindignore"]:
            ignore_path = self.workspace_root / filename
            if ignore_path.is_file():
                try:
                    with open(ignore_path, "r", encoding="utf-8") as f:
                        for line in f:
                            cleaned = line.strip()
                            if cleaned and not cleaned.startswith("#"):
                                self.patterns.append(cleaned)
                except Exception:
                    pass

    def should_ignore(self, path: Path | str) -> bool:
        """Return True if path matches default ignore sets or loaded patterns."""
        p = Path(path)
        # Check parent parts for ignored directories
        for part in p.parts:
            if part in DEFAULT_IGNORED_DIRS:
                return True

        if p.suffix.lower() in DEFAULT_IGNORED_EXTS:
            return True

        # Check loaded glob patterns
        name = p.name
        rel_str = str(p)
        for pat in self.patterns:
            if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel_str, pat):
                return True

        return False
