"""Bridge exposing connector actions as first-class CodeMind BaseTool instances."""

from __future__ import annotations

import time
from typing import Any, TYPE_CHECKING
from pydantic import BaseModel

from codemind.config import PermissionMode
from codemind.connectors.models import ActionRiskLevel, ConnectorAction
from codemind.security.permissions import PermissionLevel
from codemind.security.redaction import redact_secrets
from codemind.tools.base import BaseTool, ExecutionContext, ToolResult

if TYPE_CHECKING:
    from codemind.connectors.base import ConnectorAdapter


def make_connector_args_schema(action_name: str, schema_dict: dict[str, Any]) -> type[BaseModel]:
    """Dynamically compile a Pydantic schema model matching a connector action's arguments."""

    class DynamicActionArgs(BaseModel):
        model_config = {"extra": "allow"}

        @classmethod
        def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
            return schema_dict or {"type": "object", "properties": {}}

        @classmethod
        def model_validate(cls, obj: Any, *args: Any, **kwargs: Any) -> Any:
            if isinstance(obj, dict) and schema_dict:
                required = schema_dict.get("required", [])
                missing = [r for r in required if r not in obj]
                if missing:
                    raise ValueError(
                        f"Missing required parameter(s) for action '{action_name}': {', '.join(missing)}"
                    )
            return super().model_validate(obj, *args, **kwargs)

    clean_name = action_name.replace("-", "_").replace(".", "_")
    DynamicActionArgs.__name__ = f"Connector_{clean_name}_Args"
    return DynamicActionArgs


class ConnectorTool(BaseTool):
    """Bridges an application connector action into CodeMind's native ToolRegistry."""

    def __init__(self, adapter: ConnectorAdapter, action: ConnectorAction):
        self.adapter = adapter
        self.action = action

        # Tool naming: connector_id__action_name (e.g. gmail__search_emails)
        self.name = f"{adapter.manifest.connector_id}__{action.name}"
        self.description = f"[{adapter.manifest.icon} {adapter.manifest.name}] {action.description}"

        # Risk level mapping to PermissionLevel
        if action.risk_level == ActionRiskLevel.READ:
            self.permission_level = PermissionLevel.READ_ONLY
        elif action.risk_level == ActionRiskLevel.WRITE:
            self.permission_level = PermissionLevel.READ_WRITE
        else:  # SENSITIVE
            self.permission_level = PermissionLevel.DANGEROUS

        self.args_schema = make_connector_args_schema(self.name, action.args_schema)

    async def execute(self, arguments: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """Execute the connector action with timing, permission checks, and audit logging."""
        t0 = time.time()
        connector_id = self.adapter.manifest.connector_id
        action_name = self.action.name

        # Check permission policy and interactive approval
        pm = getattr(self.adapter, "permission_manager", None)
        mode = getattr(context.permission_checker, "mode", PermissionMode.SUPERVISED)
        if pm:
            allowed, requires_approval, reason = pm.evaluate(
                connector_id=connector_id,
                action_name=action_name,
                risk_level=self.action.risk_level,
                permission_mode=mode,
            )
            if not allowed:
                return ToolResult.error(f"Permission denied: {reason}", error_code="PERMISSION_DENIED")

            if requires_approval:
                if hasattr(context, "ui") and context.ui and hasattr(context.ui, "request_approval"):
                    approved = await context.ui.request_approval(
                        f"Execute {self.action.risk_level.value.upper()} action '{action_name}' on connector '{connector_id}'?"
                    )
                    if not approved:
                        return ToolResult.error(f"User denied approval for action '{action_name}'.", error_code="APPROVAL_REJECTED")

        try:
            res: ToolResult = await self.adapter.execute_action(action_name, arguments, context)
            duration_ms = (time.time() - t0) * 1000.0

            # Audit log
            if hasattr(self.adapter, "audit_logger") and self.adapter.audit_logger:
                self.adapter.audit_logger.log(
                    connector_id=connector_id,
                    action=action_name,
                    risk_level=self.action.risk_level,
                    approved=True,
                    ok=res.ok,
                    duration_ms=duration_ms,
                    error_code=res.error_code,
                    metadata={"arguments": arguments},
                )

            # Scrub secrets from result content
            res.content = redact_secrets(res.content)
            truncated_content, is_trunc = context.truncate_output(res.content)
            res.content = truncated_content
            res.truncated = is_trunc
            return res

        except Exception as ex:
            duration_ms = (time.time() - t0) * 1000.0
            err_msg = redact_secrets(str(ex))

            if hasattr(self.adapter, "audit_logger") and self.adapter.audit_logger:
                self.adapter.audit_logger.log(
                    connector_id=connector_id,
                    action=action_name,
                    risk_level=self.action.risk_level,
                    approved=True,
                    ok=False,
                    duration_ms=duration_ms,
                    error_code="CONNECTOR_EXECUTION_ERROR",
                    metadata={"error": err_msg},
                )

            return ToolResult.error(
                f"Connector '{connector_id}' action '{action_name}' failed: {err_msg}",
                error_code="CONNECTOR_EXECUTION_ERROR",
            )
