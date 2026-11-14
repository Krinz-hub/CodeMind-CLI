"""Unit tests for session serialization, recovery, and audit logging."""

from codemind.sessions.manager import SessionManager
from codemind.sessions.store import SessionSnapshot
from tests.base import BaseAgentTestCase


class TestSessions(BaseAgentTestCase):
    def test_save_and_load_session(self) -> None:
        mgr = SessionManager(self.workspace_root)
        snapshot = SessionSnapshot(
            session_id="cm-test-12345",
            workspace_root=str(self.workspace_root),
            model_name="codemind",
            provider="local",
            permission_mode="supervised",
            turns_completed=3,
            files_changed=["src/main.py"],
        )

        saved_path = mgr.save_checkpoint(snapshot)
        self.assertTrue(saved_path.is_file())

        loaded = mgr.load_session("cm-test-12345")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.session_id, "cm-test-12345")
        self.assertEqual(loaded.turns_completed, 3)
        self.assertEqual(loaded.files_changed, ["src/main.py"])

    def test_append_event_trace(self) -> None:
        mgr = SessionManager(self.workspace_root)
        mgr.append_event("cm-test-12345", "test_event", {"status": "ok", "key": "val"})

        trace_file = self.workspace_root / ".codemind" / "sessions" / "cm-test-12345.events.jsonl"
        self.assertTrue(trace_file.is_file())
        with open(trace_file) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("test_event", lines[0])
