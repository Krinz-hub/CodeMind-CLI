"""Event taxonomy and listener interface for runtime monitoring."""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field


class AgentEventType(str, Enum):
    SESSION_START = "session_start"
    TURN_START = "turn_start"
    MODEL_REQUEST = "model_request"
    MODEL_RESPONSE = "model_response"
    PLAN_UPDATED = "plan_updated"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    VERIFICATION_START = "verification_start"
    VERIFICATION_END = "verification_end"
    TASK_COMPLETED = "task_completed"
    TASK_PAUSED = "task_paused"
    TASK_CANCELLED = "task_cancelled"
    ERROR = "error"


class AgentEvent(BaseModel):
    timestamp: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    event_type: AgentEventType
    session_id: str
    data: dict[str, Any] = Field(default_factory=dict)


EventListener = Callable[[AgentEvent], None]
