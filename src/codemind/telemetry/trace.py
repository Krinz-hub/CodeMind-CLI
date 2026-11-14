"""Telemetry and trace exporter for evaluation and debugging."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codemind.security.redaction import redact_secrets


class TraceExporter:
    """Exports redacted audit traces for evaluation."""

    def __init__(self, trace_file: Path):
        self.trace_file = trace_file

    def export_summary(self) -> dict[str, Any]:
        """Aggregate event counts and outcomes from the trace file."""
        if not self.trace_file.is_file():
            return {"error": "Trace file not found"}

        events = []
        with open(self.trace_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))

        tool_calls = [e for e in events if e.get("event_type") == "tool_start"]
        errors = [e for e in events if e.get("event_type") == "error"]

        return {
            "total_events": len(events),
            "tool_calls_count": len(tool_calls),
            "errors_count": len(errors),
            "trace_path": str(self.trace_file),
        }
