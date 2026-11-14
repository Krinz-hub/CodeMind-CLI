"""Permission model and policy enforcement."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel

from codemind.config import PermissionMode


class PermissionLevel(str, Enum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    EXECUTE = "execute"
    DANGEROUS = "dangerous"


class PermissionDecision(BaseModel):
    allowed: bool
    requires_approval: bool
    reason: str


class PermissionChecker:
    """Enforces active permission policies on tool operations."""

    def __init__(self, mode: PermissionMode = PermissionMode.SUPERVISED):
        self.mode = mode

    def evaluate(self, level: PermissionLevel, metadata: dict[str, Any] | None = None) -> PermissionDecision:
        """Evaluate whether an action is permitted and if interactive human approval is required."""
        metadata = metadata or {}

        # 1. READ_ONLY Mode: completely disallows any write, execute, or dangerous tools
        if self.mode == PermissionMode.READ_ONLY:
            if level == PermissionLevel.READ_ONLY:
                return PermissionDecision(allowed=True, requires_approval=False, reason="Read-only operation allowed.")
            return PermissionDecision(
                allowed=False,
                requires_approval=False,
                reason=f"Action forbidden: Active permission mode is '{PermissionMode.READ_ONLY.value}'.",
            )

        # 2. SUPERVISED Mode (Default): Read is auto-allowed; Write/Execute requires explicit user approval
        if self.mode == PermissionMode.SUPERVISED:
            if level == PermissionLevel.READ_ONLY:
                return PermissionDecision(allowed=True, requires_approval=False, reason="Read-only operation allowed.")
            elif level in (PermissionLevel.READ_WRITE, PermissionLevel.EXECUTE):
                return PermissionDecision(
                    allowed=True,
                    requires_approval=True,
                    reason=f"Supervised mode requires approval for {level.value} action.",
                )
            else:  # DANGEROUS
                return PermissionDecision(
                    allowed=True,
                    requires_approval=True,
                    reason="Dangerous operation strictly requires explicit user authorization.",
                )

        # 3. TRUSTED Mode: Low-risk read/write within workspace is auto-approved; Execute / Dangerous requires approval
        if self.mode == PermissionMode.TRUSTED:
            if level in (PermissionLevel.READ_ONLY, PermissionLevel.READ_WRITE):
                return PermissionDecision(
                    allowed=True,
                    requires_approval=False,
                    reason="Trusted workspace mode permits safe internal read and write.",
                )
            else:  # EXECUTE or DANGEROUS
                return PermissionDecision(
                    allowed=True,
                    requires_approval=True,
                    reason=f"Execution of shell commands or dangerous operations requires approval even in trusted mode.",
                )

        return PermissionDecision(allowed=False, requires_approval=False, reason="Unknown permission state.")
