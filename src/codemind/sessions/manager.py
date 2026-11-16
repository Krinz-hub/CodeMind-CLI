"""Session manager for loading, checkpointing, and recovering task state."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from codemind.security.redaction import redact_secrets
from codemind.sessions.store import SessionSnapshot


class SessionManager:
    """Manages disk serialization of sessions and audit traces under .codemind/sessions/."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.sessions_dir = self.workspace_root / ".codemind" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(self, snapshot: SessionSnapshot) -> Path:
        """Write session snapshot atomically to JSON file."""
        snapshot.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        file_path = self.sessions_dir / f"{snapshot.session_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(snapshot.model_dump_json(indent=2))
        return file_path

    def load_session(self, session_id: str) -> SessionSnapshot | None:
        """Load session snapshot from disk."""
        target = self.sessions_dir / f"{session_id}.json"
        if not target.is_file():
            # Try searching for prefix if user passed short ID
            matches = list(self.sessions_dir.glob(f"*{session_id}*.json"))
            if matches:
                target = matches[0]
            else:
                return None

        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
                return SessionSnapshot.model_validate(data)
        except Exception:
            return None

    def list_sessions(self) -> list[dict[str, Any]]:
        """List recent saved sessions."""
        sessions: list[dict[str, Any]] = []
        for file in sorted(self.sessions_dir.glob("*.json"), reverse=True):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sessions.append({
                        "session_id": data.get("session_id", file.stem),
                        "updated_at": data.get("updated_at", ""),
                        "model": data.get("model_name", ""),
                        "turns": data.get("turns_completed", 0),
                        "completed": data.get("is_completed", False),
                    })
            except Exception:
                continue
        return sessions

    def append_event(self, session_id: str, event_type: str, data: dict[str, Any]) -> None:
        """Append a redacted event to the session event log."""
        log_file = self.sessions_dir / f"{session_id}.events.jsonl"
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "event_type": event_type,
            "data": data,
        }
        # Redact any sensitive content in the JSON string
        serialized = json.dumps(entry)
        clean_line = redact_secrets(serialized) + "\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(clean_line)

    def get_session_events(self, session_id: str) -> list[dict[str, Any]]:
        """Read all logged events for a session."""
        log_file = self.sessions_dir / f"{session_id}.events.jsonl"
        events: list[dict[str, Any]] = []
        if not log_file.is_file():
            return events
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        continue
        return events
