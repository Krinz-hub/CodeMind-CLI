"""Fine-grained permission policies and approval gates for connector actions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codemind.config import PermissionMode
from codemind.connectors.models import ActionRiskLevel


class ConnectorPolicy(BaseModel):
    """Per-connector permission configuration."""

    enabled: bool = True
    read_only: bool = False
    disabled_actions: list[str] = Field(default_factory=list)
    supervised_actions: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    blocked_actions: list[str] = Field(default_factory=list)


class ConnectorPermissionManager:
    """Enforces risk tiers, interactive approvals, and per-connector policies."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.config_file = self.workspace_root / ".codemind" / "connectors_policy.json"
        self._policies: dict[str, ConnectorPolicy] = {}
        self.load_policies()

    def load_policies(self) -> None:
        """Load connector policies from disk."""
        if not self.config_file.is_file():
            return
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._policies = {
                    cid: ConnectorPolicy.model_validate(p)
                    for cid, p in data.items()
                }
        except Exception:
            self._policies = {}

    def save_policies(self) -> None:
        """Persist connector policies to disk."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            data = {cid: p.model_dump() for cid, p in self._policies.items()}
            json.dump(data, f, indent=2)

    def get_policy(self, connector_id: str) -> ConnectorPolicy:
        """Get or initialize policy for a connector."""
        if connector_id not in self._policies:
            self._policies[connector_id] = ConnectorPolicy()
        return self._policies[connector_id]

    def set_policy(self, connector_id: str, policy: ConnectorPolicy) -> None:
        """Set or update policy for a connector."""
        self._policies[connector_id] = policy
        self.save_policies()

    def set_enabled(self, connector_id: str, enabled: bool) -> None:
        policy = self.get_policy(connector_id)
        policy.enabled = enabled
        self.save_policies()

    def set_read_only(self, connector_id: str, read_only: bool) -> None:
        policy = self.get_policy(connector_id)
        policy.read_only = read_only
        self.save_policies()

    def disable_action(self, connector_id: str, action_name: str) -> None:
        policy = self.get_policy(connector_id)
        if action_name not in policy.disabled_actions:
            policy.disabled_actions.append(action_name)
            self.save_policies()

    def enable_action(self, connector_id: str, action_name: str) -> None:
        policy = self.get_policy(connector_id)
        if action_name in policy.disabled_actions:
            policy.disabled_actions.remove(action_name)
            self.save_policies()

    def check_permission(
        self,
        connector_id: str,
        action_name: str,
        risk_level: ActionRiskLevel,
        permission_mode: PermissionMode = PermissionMode.SUPERVISED,
    ) -> tuple[bool, str]:
        """Check if action is allowed by policy, returning (allowed, reason)."""
        allowed, _, reason = self.evaluate(connector_id, action_name, risk_level, permission_mode)
        return allowed, reason

    def evaluate(
        self,
        connector_id: str,
        action_name: str,
        risk_level: ActionRiskLevel,
        permission_mode: PermissionMode = PermissionMode.SUPERVISED,
    ) -> tuple[bool, bool, str]:
        """Evaluate if an action is allowed and if explicit user approval is required.

        Returns: (allowed, requires_approval, reason)
        """
        policy = self.get_policy(connector_id)

        # 1. Check connector enabled
        if not policy.enabled:
            return False, False, f"Connector '{connector_id}' is disabled by user policy."

        # 2. Check action enabled
        if action_name in policy.disabled_actions:
            return False, False, f"Action '{action_name}' on connector '{connector_id}' is explicitly disabled."

        # 3. Check connector read_only enforcement
        if policy.read_only and risk_level != ActionRiskLevel.READ:
            return False, False, f"Connector '{connector_id}' is locked in read-only mode."

        # 4. Global READ_ONLY mode blocks writes and sensitive actions
        if permission_mode == PermissionMode.READ_ONLY and risk_level != ActionRiskLevel.READ:
            return False, False, f"Active system permission mode is 'read_only'."

        # 5. SENSITIVE risk level strictly requires interactive human approval
        if risk_level == ActionRiskLevel.SENSITIVE:
            return True, True, f"Sensitive action '{action_name}' on '{connector_id}' strictly requires user approval."

        # 6. WRITE risk level requires approval in SUPERVISED mode
        if risk_level == ActionRiskLevel.WRITE:
            req_appr = (permission_mode == PermissionMode.SUPERVISED)
            return True, req_appr, f"Write action '{action_name}' on '{connector_id}'."

        # 7. READ is auto-allowed
        return True, False, f"Read action '{action_name}' on '{connector_id}' permitted."
