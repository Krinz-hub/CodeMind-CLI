# Connector Development Guide

## 1. Overview

This guide explains how to author and register a new native application connector in CodeMind CLI.

All native connectors inherit from `ConnectorAdapter` and define a static `manifest: ConnectorManifest`.

---

## 2. Step-by-Step Implementation

### Step 1: Define Connector Manifest

Create your adapter file under `src/codemind/connectors/native/<name>.py`:

```python
from codemind.connectors.base import ConnectorAdapter
from codemind.connectors.models import (
    ActionRiskLevel,
    AuthMethod,
    ConnectorAction,
    ConnectorHealth,
    ConnectorManifest,
)
from codemind.tools.base import ExecutionContext, ToolResult

class CustomAppConnector(ConnectorAdapter):
    manifest = ConnectorManifest(
        connector_id="custom_app",
        name="Custom App",
        description="Interact with Custom App records and resources.",
        category="productivity",
        version="1.0.0",
        icon="⚡",
        auth_method=AuthMethod.API_KEY,
        actions=[
            ConnectorAction(
                name="list_items",
                description="List items in Custom App.",
                risk_level=ActionRiskLevel.READ,
                args_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 20},
                    },
                },
            ),
            ConnectorAction(
                name="publish_post",
                description="Publish an announcement (SENSITIVE).",
                risk_level=ActionRiskLevel.SENSITIVE,
                args_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["title", "content"],
                },
            ),
        ],
    )
```

### Step 2: Implement Health Checking

`check_health()` is called during `codemind connectors test <id>` and when verifying token health:

```python
    async def check_health(self) -> ConnectorHealth:
        if not self.is_connected():
            return ConnectorHealth(
                healthy=False,
                status=ConnectionStatus.DISCONNECTED,
                message="API key not configured.",
            )

        token = await self.auth_manager.get_valid_access_token(self.connector_id)
        # Ping provider ping/user endpoint with token
        ...
        return ConnectorHealth(healthy=True, status=ConnectionStatus.CONNECTED, message="Connected.")
```

### Step 3: Implement `execute_action`

Handle action dispatch and return normalized `ToolResult.success(...)` or `ToolResult.error(...)`:

```python
    async def execute_action(
        self,
        action_name: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        if action_name == "list_items":
            return await self._list_items(arguments, context)
        elif action_name == "publish_post":
            return await self._publish_post(arguments, context)
        return ToolResult.error(f"Unknown action '{action_name}'.")
```

### Step 4: Register in `ConnectorManager`

Add registration in `src/codemind/connectors/manager.py`:

```python
try:
    from codemind.connectors.native.custom_app import CustomAppConnector
    self.registry.register(CustomAppConnector)
except ImportError:
    pass
```

---

## 3. Best Practices Checklist

- [ ] Declare appropriate `risk_level` (`READ`, `WRITE`, `SENSITIVE`) on every action.
- [ ] Provide clear JSON Schema parameter descriptions with `type` and `required`.
- [ ] Never log or print raw tokens or authorization headers in errors.
- [ ] Validate HTTP status codes and handle rate limits or network failures gracefully.
- [ ] Write hermetic mocked unit tests in `tests/connectors/`.
