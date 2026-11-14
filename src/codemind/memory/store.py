"""Scoped project memory store."""

from __future__ import annotations

import json
from pathlib import Path


class ProjectMemory:
    """Stores key-value project facts in .codemind/memory/facts.json."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.memory_file = self.workspace_root / ".codemind" / "memory" / "facts.json"
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        self.facts: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self.memory_file.is_file():
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    self.facts = json.load(f)
            except Exception:
                self.facts = {}

    def save(self) -> None:
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(self.facts, f, indent=2)

    def set_fact(self, key: str, value: str) -> None:
        self.facts[key] = value
        self.save()

    def get_fact(self, key: str) -> str | None:
        return self.facts.get(key)

    def list_facts(self) -> dict[str, str]:
        return dict(self.facts)
