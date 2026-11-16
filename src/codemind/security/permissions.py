"""Permission model and policy enforcement (Phase D Workstream K)."""

from __future__ import annotations

from enum import Enum
import fnmatch
import json
from pathlib import Path
import shlex
from typing import Any

from pydantic import BaseModel, Field
import yaml

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


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class PermissionRule(BaseModel):
    """Rule matching a specific tool, command prefix, or path pattern."""

    tool: str | None = None
    command_prefix: list[str] | None = None
    path_pattern: str | None = None
    scope: str = "current_workspace"
    decision: PolicyDecision = PolicyDecision.ASK
    reason: str | None = None


class PermissionPolicyEngine:
    """Evaluates fine-grained declarative security policies against tool invocations."""

    def __init__(self, rules: list[PermissionRule] | None = None):
        self.rules: list[PermissionRule] = rules or []

    @classmethod
    def load_from_workspace(cls, workspace_root: Path) -> PermissionPolicyEngine:
        """Load policy rules from .codemind/permissions.yaml or permissions.json."""
        ws = workspace_root.resolve()
        yaml_p = ws / ".codemind" / "permissions.yaml"
        json_p = ws / ".codemind" / "permissions.json"

        target_file: Path | None = None
        if yaml_p.is_file():
            target_file = yaml_p
        elif json_p.is_file():
            target_file = json_p

        if not target_file:
            return cls()

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                if target_file.suffix in (".yaml", ".yml"):
                    data = yaml.safe_load(f) or {}
                else:
                    data = json.load(f) or {}

            raw_rules = data.get("rules", [])
            rules: list[PermissionRule] = []
            for r in raw_rules:
                if isinstance(r, dict):
                    rules.append(PermissionRule.model_validate(r))
            return cls(rules=rules)
        except Exception:
            return cls()

    def evaluate(self, tool_name: str, arguments: dict[str, Any]) -> PermissionDecision | None:
        """Evaluate invocation against configured policy rules in priority order."""
        for rule in self.rules:
            if not self._matches_rule(rule, tool_name, arguments):
                continue

            reason_prefix = rule.reason or f"Rule matched for '{tool_name}'"

            if rule.decision == PolicyDecision.ALLOW:
                return PermissionDecision(
                    allowed=True,
                    requires_approval=False,
                    reason=f"Policy ALLOW: {reason_prefix}.",
                )
            elif rule.decision == PolicyDecision.DENY:
                return PermissionDecision(
                    allowed=False,
                    requires_approval=False,
                    reason=f"Policy DENY: {reason_prefix}.",
                )
            elif rule.decision == PolicyDecision.ASK:
                return PermissionDecision(
                    allowed=True,
                    requires_approval=True,
                    reason=f"Policy ASK: {reason_prefix} requires explicit authorization.",
                )

        return None

    def _matches_rule(self, rule: PermissionRule, tool_name: str, arguments: dict[str, Any]) -> bool:
        """Check whether a rule matches the given tool and invocation arguments."""
        # 1. Match tool name if specified
        if rule.tool:
            # Normalize terminal / run_command aliases
            tool_normalized = "terminal" if tool_name == "run_command" else tool_name
            rule_tool_normalized = "terminal" if rule.tool == "run_command" else rule.tool
            if tool_normalized != rule_tool_normalized:
                return False

        # 2. Match command prefix if specified (for run_command/terminal)
        if rule.command_prefix:
            cmd_raw = arguments.get("command") or arguments.get("cmd") or ""
            if not cmd_raw:
                return False

            try:
                tokens = shlex.split(cmd_raw)
            except Exception:
                tokens = cmd_raw.split()

            if len(tokens) < len(rule.command_prefix):
                return False

            if tokens[: len(rule.command_prefix)] != rule.command_prefix:
                return False

        # 3. Match path pattern if specified (for file operations)
        if rule.path_pattern:
            path_val = arguments.get("path") or arguments.get("file_path") or ""
            if not path_val or not fnmatch.fnmatch(str(path_val), rule.path_pattern):
                return False

        return True


class PermissionChecker:
    """Enforces active permission policies on tool operations."""

    def __init__(
        self,
        mode: PermissionMode = PermissionMode.SUPERVISED,
        policy: PermissionPolicyEngine | None = None,
        workspace_root: Path | None = None,
    ):
        self.mode = mode
        if policy is not None:
            self.policy = policy
        elif workspace_root is not None:
            self.policy = PermissionPolicyEngine.load_from_workspace(workspace_root)
        else:
            self.policy = None

    def evaluate(self, level: PermissionLevel, metadata: dict[str, Any] | None = None) -> PermissionDecision:
        """Evaluate whether an action is permitted and if interactive human approval is required."""
        metadata = metadata or {}
        tool_name = metadata.get("tool", "")
        arguments = metadata.get("arguments", {})

        # 0. Fine-grained custom policy rules take precedence if present
        if self.policy:
            policy_decision = self.policy.evaluate(tool_name, arguments)
            if policy_decision is not None:
                return policy_decision

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
                    reason="Execution of shell commands or dangerous operations requires approval even in trusted mode.",
                )

        return PermissionDecision(allowed=False, requires_approval=False, reason="Unknown permission state.")
