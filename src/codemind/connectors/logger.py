"""Audit logging engine for connector invocations with automatic secret redaction."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from codemind.connectors.models import ActionRiskLevel
from codemind.security.redaction import redact_secrets


class ConnectorAuditLogger:
    """Records immutable, secret-scrubbed audit trails of all connector actions."""

    def __init__(self, log_path: Path):
        self.log_path = log_path.resolve()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        connector_id: str,
        action: str,
        risk_level: ActionRiskLevel,
        approved: bool,
        ok: bool,
        duration_ms: float,
        error_code: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Append a scrubbed audit record."""
        # Sanitize metadata
        clean_metadata: dict[str, Any] = {}
        if metadata:
            for k, v in metadata.items():
                if any(s in k.lower() for s in ["token", "key", "secret", "auth", "pass"]):
                    clean_metadata[k] = "[REDACTED]"
                elif isinstance(v, str):
                    clean_metadata[k] = redact_secrets(v)
                else:
                    clean_metadata[k] = v

        record = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "connector_id": connector_id,
            "action": action,
            "risk_level": risk_level.value,
            "approved": approved,
            "ok": ok,
            "duration_ms": round(duration_ms, 2),
            "error_code": error_code,
            "metadata": clean_metadata,
        }

        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass

    def get_recent_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve recent audit events."""
        if not self.log_path.is_file():
            return []

        records: list[dict[str, Any]] = []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception:
            return []

        return records[-limit:]
