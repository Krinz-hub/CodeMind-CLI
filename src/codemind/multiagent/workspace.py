"""Isolated worker workspace provisioning, diff tracking, and integration merging."""

from __future__ import annotations

import difflib
import os
import shutil
from pathlib import Path
from typing import Any

from codemind.multiagent.models import ChangeProposal


class WorkerWorkspaceManager:
    """Manages isolated disk sandboxes for worker agents and safe integration into primary workspace."""

    def __init__(self, primary_workspace_root: Path):
        self.primary_root = primary_workspace_root.resolve()
        self.workspaces_base = self.primary_root / ".codemind" / "workspaces"
        self.workspaces_base.mkdir(parents=True, exist_ok=True)
        self._snapshots: dict[str, dict[str, str]] = {}  # worker_id -> {relative_path: content}

    def provision_worker_workspace(self, worker_id: str, relevant_files: list[str] | None = None) -> Path:
        """Create an isolated workspace mirror for a worker agent."""
        worker_dir = self.workspaces_base / worker_id
        if worker_dir.exists():
            shutil.rmtree(worker_dir, ignore_errors=True)
        worker_dir.mkdir(parents=True, exist_ok=True)

        # Copy existing workspace files to provide context, ignoring .git and .codemind
        snapshot: dict[str, str] = {}
        for root, dirs, files in os.walk(self.primary_root):
            # Prune hidden and build dirs
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", "venv", ".venv")]
            rel_dir = Path(root).relative_to(self.primary_root)
            if str(rel_dir).startswith(".codemind") or str(rel_dir).startswith(".git"):
                continue

            target_dir = worker_dir / rel_dir
            target_dir.mkdir(parents=True, exist_ok=True)

            for f in files:
                if f.startswith("."):
                    continue
                src_file = Path(root) / f
                dst_file = target_dir / f
                try:
                    content = src_file.read_text(encoding="utf-8", errors="replace")
                    dst_file.write_text(content, encoding="utf-8")
                    rel_path = str((rel_dir / f).as_posix())
                    if rel_path.startswith("./"):
                        rel_path = rel_path[2:]
                    snapshot[rel_path] = content
                except Exception:
                    pass

        self._snapshots[worker_id] = snapshot
        return worker_dir

    def extract_change_proposal(self, worker_id: str, task_id: str) -> ChangeProposal:
        """Scan worker workspace, detect created/modified files, and compute unified diffs."""
        worker_dir = self.workspaces_base / worker_id
        snapshot = self._snapshots.get(worker_id, {})
        created_files: list[str] = []
        modified_files: list[str] = []
        diffs: dict[str, str] = {}

        if not worker_dir.exists():
            return ChangeProposal(worker_id=worker_id, task_id=task_id)

        for root, dirs, files in os.walk(worker_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules")]
            rel_dir = Path(root).relative_to(worker_dir)
            if str(rel_dir).startswith(".codemind") or str(rel_dir).startswith(".git"):
                continue

            for f in files:
                if f.startswith("."):
                    continue
                file_path = Path(root) / f
                rel_path = str((rel_dir / f).as_posix())
                if rel_path.startswith("./"):
                    rel_path = rel_path[2:]

                try:
                    new_content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                if rel_path not in snapshot:
                    created_files.append(rel_path)
                    # Diff from empty
                    diff = difflib.unified_diff(
                        [],
                        new_content.splitlines(keepends=True),
                        fromfile="/dev/null",
                        tofile=rel_path,
                    )
                    diffs[rel_path] = "".join(diff)
                elif snapshot[rel_path] != new_content:
                    modified_files.append(rel_path)
                    diff = difflib.unified_diff(
                        snapshot[rel_path].splitlines(keepends=True),
                        new_content.splitlines(keepends=True),
                        fromfile=f"a/{rel_path}",
                        tofile=f"b/{rel_path}",
                    )
                    diffs[rel_path] = "".join(diff)

        summary = f"Worker {worker_id} proposed {len(created_files)} created and {len(modified_files)} modified files."
        return ChangeProposal(
            worker_id=worker_id,
            task_id=task_id,
            created_files=created_files,
            modified_files=modified_files,
            diffs=diffs,
            summary=summary,
        )

    def detect_conflicts(self, proposals: list[ChangeProposal]) -> list[str]:
        """Detect overlapping file mutations between multiple worker proposals."""
        conflicts: list[str] = []
        file_owners: dict[str, str] = {}

        for prop in proposals:
            all_mutated = set(prop.created_files + prop.modified_files)
            for f in all_mutated:
                if f in file_owners:
                    conflicts.append(
                        f"Conflict on '{f}': Mutated concurrently by worker '{file_owners[f]}' and '{prop.worker_id}'"
                    )
                else:
                    file_owners[f] = prop.worker_id

        return conflicts

    def apply_proposal_to_primary(self, proposal: ChangeProposal) -> tuple[bool, str]:
        """Apply approved change proposal to the primary integration workspace."""
        worker_dir = self.workspaces_base / proposal.worker_id
        if not worker_dir.exists():
            return False, f"Worker workspace for '{proposal.worker_id}' does not exist."

        for rel_path in proposal.created_files + proposal.modified_files:
            src_file = worker_dir / rel_path
            dst_file = self.primary_root / rel_path
            if not src_file.exists():
                continue
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)

        return True, f"Successfully merged {len(proposal.created_files)} created and {len(proposal.modified_files)} modified files."

    def cleanup_worker_workspace(self, worker_id: str) -> None:
        """Remove worker isolated workspace directory."""
        worker_dir = self.workspaces_base / worker_id
        if worker_dir.exists():
            shutil.rmtree(worker_dir, ignore_errors=True)
        self._snapshots.pop(worker_id, None)
