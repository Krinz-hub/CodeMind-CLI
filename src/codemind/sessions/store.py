"""Session persistence model and JSON serialization."""

from __future__ import annotations

import datetime
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SessionSnapshot(BaseModel):
    session_id: str = Field(
        default_factory=lambda: f"cm-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    )
    workspace_root: str
    created_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    model_name: str
    provider: str
    permission_mode: str
    plan: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    turns_completed: int = 0
    is_completed: bool = False
