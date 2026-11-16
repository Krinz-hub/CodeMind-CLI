"""Runtime state representations for the active agent session."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codemind.models.base import ChatMessage
from codemind.planning.task import TaskPlan


class AgentState(BaseModel):
    """Authoritative ephemeral state for an in-flight agent session."""

    session_id: str
    workspace_root: str
    task_instruction: str = ""
    turn_count: int = 0
    total_tool_calls: int = 0
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    messages: list[ChatMessage] = Field(default_factory=list)
    plan: TaskPlan = Field(default_factory=TaskPlan)
    is_complete: bool = False
    is_paused: bool = False
    is_cancelled: bool = False
    current_task_id: str | None = None
    status: str = "running"
    expected_files: list[str] = Field(default_factory=list)
    criteria_verified: bool = False
    final_content: str = ""
    final_summary: list[str] = Field(default_factory=list)

    def record_file_created(self, path: str) -> None:
        if path not in self.files_created:
            self.files_created.append(path)

    def record_file_modified(self, path: str) -> None:
        if path not in self.files_modified:
            self.files_modified.append(path)

    def add_message(self, role: str, content: str, name: str | None = None) -> None:
        self.messages.append(ChatMessage(role=role, content=content, name=name))
