"""Workspace path sandboxing, canonicalization, and secret file detection."""

from __future__ import annotations

import os
from pathlib import Path


class SecurityViolationError(Exception):
    """Raised when an operation attempts to breach workspace or security boundaries."""


# Denied secret files and sensitive pattern extensions
SECRET_PATTERNS = [
    ".env",
    ".env.",
    "id_rsa",
    "id_ed25519",
    "id_dsa",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    "credentials.json",
    "client_secret.json",
    "service_account.json",
    "token.json",
    "passwd",
    "shadow",
]


class WorkspaceSandbox:
    """Enforces strict file boundary and secret shielding within designated workspace."""

    def __init__(self, workspace_root: str | Path, allow_external: bool = False):
        self.workspace_root = Path(workspace_root).resolve()
        self.allow_external = allow_external

    def canonicalize(self, target_path: str | Path) -> Path:
        """Resolve absolute canonical real path, resolving symlinks and eliminating traversal."""
        path_obj = Path(target_path)
        if not path_obj.is_absolute():
            resolved = (self.workspace_root / path_obj).resolve()
        else:
            resolved = path_obj.resolve()
        return resolved

    def is_within_workspace(self, target_path: str | Path) -> bool:
        """Verify whether canonicalized path resides inside the workspace directory."""
        if self.allow_external:
            return True
        canonical = self.canonicalize(target_path)
        try:
            canonical.relative_to(self.workspace_root)
            return True
        except ValueError:
            return False

    def is_secret_file(self, target_path: str | Path) -> bool:
        """Check if filename matches sensitive secret or credential patterns."""
        p = Path(target_path)
        name_lower = p.name.lower()
        for pattern in SECRET_PATTERNS:
            if pattern in name_lower:
                return True
        return False

    def validate_path_access(self, target_path: str | Path, is_write: bool = False) -> Path:
        """Assert path safety. Raises SecurityViolationError if boundary or secret rules are violated."""
        p_obj = Path(target_path)
        raw_full = (self.workspace_root / p_obj) if not p_obj.is_absolute() else p_obj

        # Check symlink destination if file or path is a symlink
        if raw_full.is_symlink() or os.path.islink(raw_full):
            real_target = Path(os.path.realpath(raw_full))
            if not self.is_within_workspace(real_target):
                raise SecurityViolationError(
                    f"Symlink escape detected: symlink '{target_path}' points outside workspace root."
                )

        canonical = self.canonicalize(target_path)

        if not self.is_within_workspace(canonical):
            raise SecurityViolationError(
                f"Path traversal detected: '{target_path}' resolves outside workspace root "
                f"('{self.workspace_root}')."
            )

        if self.is_secret_file(canonical):
            raise SecurityViolationError(
                f"Access denied: '{target_path}' matches protected secret file pattern."
            )

        return canonical
