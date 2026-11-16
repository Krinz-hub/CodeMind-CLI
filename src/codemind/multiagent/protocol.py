"""Inter-Agent Communication Protocol (IACP v1) validation and mediation."""

from __future__ import annotations

import json
from typing import Any

from codemind.multiagent.models import InterAgentMessage, MessageType
from codemind.security.redaction import redact_secrets


class ProtocolViolationError(Exception):
    """Raised when an inter-agent message violates protocol invariants."""


class MessageRouter:
    """Validates and enforces coordinator mediation over all inter-agent messages."""

    def __init__(self):
        self.message_history: list[InterAgentMessage] = []

    def validate_and_route(self, message: InterAgentMessage) -> InterAgentMessage:
        """Validate routing constraints and record message into audit history."""
        # Invariant 1: Workers cannot instruct other workers directly
        sender = message.sender_agent.strip().lower()
        recipient = message.recipient.strip().lower()

        is_coordinator_involved = sender == "coordinator" or recipient == "coordinator"
        if not is_coordinator_involved:
            raise ProtocolViolationError(
                f"Unauthorized direct worker-to-worker message: '{sender}' attempted to contact '{recipient}' without coordinator mediation."
            )

        # Invariant 2: Only coordinator can assign tasks
        if message.message_type == MessageType.TASK_ASSIGNMENT and sender != "coordinator":
            raise ProtocolViolationError(
                f"Security violation: Worker '{sender}' cannot issue TASK_ASSIGNMENT. Only coordinator can delegate work."
            )

        # Record into history
        self.message_history.append(message)
        return message

    def get_messages_for_task(self, task_id: str) -> list[InterAgentMessage]:
        """Retrieve full conversation trace for a specific task."""
        return [m for m in self.message_history if m.task_id == task_id]

    def get_messages_for_worker(self, worker_id: str) -> list[InterAgentMessage]:
        """Retrieve messages sent to or from a specific worker."""
        clean_id = worker_id.strip().lower()
        return [
            m for m in self.message_history
            if m.sender_agent.strip().lower() == clean_id or m.recipient.strip().lower() == clean_id
        ]
