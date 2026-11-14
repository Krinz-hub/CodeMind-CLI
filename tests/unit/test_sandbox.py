"""Unit tests for workspace sandboxing and traversal checks."""

from pathlib import Path

from codemind.security.sandbox import SecurityViolationError, WorkspaceSandbox
from tests.base import BaseAgentTestCase


class TestSandbox(BaseAgentTestCase):
    def test_canonicalize_and_containment(self) -> None:
        self.create_file("src/main.py", "print('hello')")
        valid = self.sandbox.validate_path_access("src/main.py")
        self.assertEqual(valid, (self.workspace_root / "src/main.py").resolve())

    def test_path_traversal_detection(self) -> None:
        with self.assertRaises(SecurityViolationError) as ctx:
            self.sandbox.validate_path_access("../../etc/passwd")
        self.assertIn("Path traversal detected", str(ctx.exception))

    def test_secret_file_blocking(self) -> None:
        self.create_file(".env", "SECRET=12345")
        with self.assertRaises(SecurityViolationError) as ctx:
            self.sandbox.validate_path_access(".env")
        self.assertIn("protected secret file pattern", str(ctx.exception))

    def test_symlink_escape_blocking(self) -> None:
        outside_target = Path("/tmp/outside_test.txt")
        outside_target.write_text("sensitive")
        symlink_path = self.workspace_root / "escape_link.txt"
        try:
            symlink_path.symlink_to(outside_target)
            with self.assertRaises(SecurityViolationError) as ctx:
                self.sandbox.validate_path_access("escape_link.txt")
            self.assertIn("Symlink escape detected", str(ctx.exception))
        finally:
            if outside_target.exists():
                outside_target.unlink()
