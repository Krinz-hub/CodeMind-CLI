"""SQLite-backed persistent project memory store with FTS5 full-text search."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codemind.context.discovery import ProjectSummary
from codemind.memory.models import (
    MemoryEntry,
    MemoryLayer,
    MemorySearchResult,
    MemoryStats,
    MemoryStatus,
)
from codemind.security.redaction import redact_secrets

CURRENT_SCHEMA_VERSION = 1


class SQLiteProjectMemory:
    """ACID-compliant, project-isolated persistent memory engine using SQLite 3 and FTS5."""

    def __init__(self, workspace_root: Path, db_filename: str = "project_memory.db"):
        self.workspace_root = workspace_root.resolve()
        self.memory_dir = self.workspace_root / ".codemind" / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.memory_dir / db_filename
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a configured SQLite connection with WAL mode enabled."""
        con = sqlite3.connect(str(self.db_path), timeout=30.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        con.execute("PRAGMA foreign_keys=ON;")
        return con

    def _init_db(self) -> None:
        """Initialize database schema, migrations, and FTS5 full-text index."""
        with self._get_connection() as con:
            cur = con.cursor()
            # 1. Schema version
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                """
            )

            # 2. Memory entries
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id TEXT PRIMARY KEY,
                    layer TEXT NOT NULL CHECK(layer IN ('project', 'decision', 'task', 'instruction')),
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    source TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'superseded', 'deprecated')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    pinned INTEGER NOT NULL DEFAULT 0
                );
                """
            )

            # 3. FTS5 Virtual Table for full-text lexical ranking
            cur.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    id UNINDEXED,
                    title,
                    content,
                    category,
                    content='memory_entries',
                    content_rowid='rowid'
                );
                """
            )

            # 4. Triggers to maintain FTS synchronization
            cur.execute(
                """
                CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory_entries BEGIN
                    INSERT INTO memory_fts(rowid, id, title, content, category)
                    VALUES (new.rowid, new.id, new.title, new.content, new.category);
                END;
                """
            )
            cur.execute(
                """
                CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory_entries BEGIN
                    INSERT INTO memory_fts(memory_fts, rowid, id, title, content, category)
                    VALUES('delete', old.rowid, old.id, old.title, old.content, old.category);
                END;
                """
            )
            cur.execute(
                """
                CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memory_entries BEGIN
                    INSERT INTO memory_fts(memory_fts, rowid, id, title, content, category)
                    VALUES('delete', old.rowid, old.id, old.title, old.content, old.category);
                    INSERT INTO memory_fts(rowid, id, title, content, category)
                    VALUES (new.rowid, new.id, new.title, new.content, new.category);
                END;
                """
            )

            # Record initial schema version if empty
            cur.execute("SELECT version FROM schema_version WHERE version = ?", (CURRENT_SCHEMA_VERSION,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (CURRENT_SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
                )
            con.commit()

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        """Convert SQLite row to MemoryEntry model."""
        meta = {}
        try:
            meta = json.loads(row["metadata_json"])
        except Exception:
            pass

        return MemoryEntry(
            id=row["id"],
            layer=MemoryLayer(row["layer"]),
            category=row["category"],
            title=row["title"],
            content=row["content"],
            metadata=meta,
            source=row["source"],
            status=MemoryStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            confidence=float(row["confidence"]),
            pinned=bool(row["pinned"]),
        )

    def add_entry(self, entry: MemoryEntry, upsert: bool = True) -> MemoryEntry:
        """Add a memory entry with secret redaction and atomic persistence."""
        # Redact secrets before persistence
        clean_title = redact_secrets(entry.title)
        clean_content = redact_secrets(entry.content)
        clean_metadata_str = redact_secrets(json.dumps(entry.metadata))
        clean_metadata = json.loads(clean_metadata_str)

        clean_entry = entry.model_copy(
            update={
                "title": clean_title,
                "content": clean_content,
                "metadata": clean_metadata,
            }
        )

        with self._get_connection() as con:
            cur = con.cursor()
            if upsert:
                cur.execute(
                    """
                    INSERT INTO memory_entries (
                        id, layer, category, title, content, metadata_json,
                        source, status, created_at, updated_at, confidence, pinned
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        layer=excluded.layer,
                        category=excluded.category,
                        title=excluded.title,
                        content=excluded.content,
                        metadata_json=excluded.metadata_json,
                        source=excluded.source,
                        status=excluded.status,
                        updated_at=excluded.updated_at,
                        confidence=excluded.confidence,
                        pinned=excluded.pinned;
                    """,
                    (
                        clean_entry.id,
                        clean_entry.layer.value,
                        clean_entry.category,
                        clean_entry.title,
                        clean_entry.content,
                        clean_metadata_str,
                        clean_entry.source,
                        clean_entry.status.value,
                        clean_entry.created_at,
                        clean_entry.updated_at,
                        clean_entry.confidence,
                        1 if clean_entry.pinned else 0,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO memory_entries (
                        id, layer, category, title, content, metadata_json,
                        source, status, created_at, updated_at, confidence, pinned
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        clean_entry.id,
                        clean_entry.layer.value,
                        clean_entry.category,
                        clean_entry.title,
                        clean_entry.content,
                        clean_metadata_str,
                        clean_entry.source,
                        clean_entry.status.value,
                        clean_entry.created_at,
                        clean_entry.updated_at,
                        clean_entry.confidence,
                        1 if clean_entry.pinned else 0,
                    ),
                )
            con.commit()

        return clean_entry

    def get_entry(self, entry_id: str) -> MemoryEntry | None:
        """Retrieve a specific memory entry by ID."""
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM memory_entries WHERE id = ?", (entry_id,))
            row = cur.fetchone()
            if row:
                return self._row_to_entry(row)
        return None

    def update_entry(
        self,
        entry_id: str,
        title: str | None = None,
        content: str | None = None,
        status: MemoryStatus | str | None = None,
        pinned: bool | None = None,
        metadata: dict[str, Any] | None = None,
        confidence: float | None = None,
    ) -> MemoryEntry | None:
        """Update fields of an existing memory entry."""
        existing = self.get_entry(entry_id)
        if not existing:
            return None

        new_title = redact_secrets(title) if title is not None else existing.title
        new_content = redact_secrets(content) if content is not None else existing.content
        new_status = MemoryStatus(status) if status is not None else existing.status
        new_pinned = pinned if pinned is not None else existing.pinned
        new_confidence = confidence if confidence is not None else existing.confidence

        merged_metadata = dict(existing.metadata)
        if metadata is not None:
            clean_meta_str = redact_secrets(json.dumps(metadata))
            merged_metadata.update(json.loads(clean_meta_str))

        now_str = datetime.now(timezone.utc).isoformat()

        updated_entry = existing.model_copy(
            update={
                "title": new_title,
                "content": new_content,
                "status": new_status,
                "pinned": new_pinned,
                "metadata": merged_metadata,
                "confidence": new_confidence,
                "updated_at": now_str,
            }
        )

        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute(
                """
                UPDATE memory_entries SET
                    title = ?,
                    content = ?,
                    metadata_json = ?,
                    status = ?,
                    pinned = ?,
                    confidence = ?,
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    updated_entry.title,
                    updated_entry.content,
                    json.dumps(updated_entry.metadata),
                    updated_entry.status.value,
                    1 if updated_entry.pinned else 0,
                    updated_entry.confidence,
                    updated_entry.updated_at,
                    entry_id,
                ),
            )
            con.commit()

        return updated_entry

    def delete_entry(self, entry_id: str) -> bool:
        """Delete an entry by ID."""
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("DELETE FROM memory_entries WHERE id = ?", (entry_id,))
            con.commit()
            return cur.rowcount > 0

    def list_entries(
        self,
        layer: MemoryLayer | str | None = None,
        status: MemoryStatus | str | None = None,
        limit: int = 100,
    ) -> list[MemoryEntry]:
        """List memory entries with optional filtering by layer and status."""
        query = "SELECT * FROM memory_entries WHERE 1=1"
        params: list[Any] = []

        if layer:
            layer_val = layer.value if isinstance(layer, MemoryLayer) else str(layer)
            query += " AND layer = ?"
            params.append(layer_val)

        if status:
            status_val = status.value if isinstance(status, MemoryStatus) else str(status)
            query += " AND status = ?"
            params.append(status_val)

        query += " ORDER BY pinned DESC, updated_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute(query, params)
            return [self._row_to_entry(row) for row in cur.fetchall()]

    def search(
        self,
        query: str,
        layer: MemoryLayer | str | None = None,
        status: MemoryStatus | str | None = MemoryStatus.ACTIVE,
        limit: int = 10,
    ) -> list[MemorySearchResult]:
        """Perform full-text search with BM25 scoring and staleness detection."""
        results: list[MemorySearchResult] = []
        if not query or not query.strip():
            # Return most recent if query is blank
            entries = self.list_entries(layer=layer, status=status, limit=limit)
            for e in entries:
                is_stale = self.check_stale(e)
                results.append(
                    MemorySearchResult(
                        entry=e,
                        score=1.0 if e.pinned else 0.5,
                        match_reason="default_recency",
                        is_stale=is_stale,
                    )
                )
            return results

        # Clean search query for FTS5 syntax
        # Remove chars that cause FTS5 syntax errors: * " ( ) : ^
        sanitized_terms = [t for t in "".join(c if c.isalnum() or c in " _-" else " " for c in query).split() if t]
        if not sanitized_terms:
            return []

        fts_query = " OR ".join(f'"{term}"' for term in sanitized_terms)

        layer_filter = ""
        params: list[Any] = [fts_query]

        if layer:
            layer_val = layer.value if isinstance(layer, MemoryLayer) else str(layer)
            layer_filter += " AND e.layer = ?"
            params.append(layer_val)

        if status:
            status_val = status.value if isinstance(status, MemoryStatus) else str(status)
            layer_filter += " AND e.status = ?"
            params.append(status_val)

        params.append(limit)

        sql = f"""
            SELECT e.*, bm25(memory_fts) as rank
            FROM memory_fts f
            JOIN memory_entries e ON f.id = e.id
            WHERE memory_fts MATCH ?
            {layer_filter}
            ORDER BY e.pinned DESC, rank ASC
            LIMIT ?;
        """

        try:
            with self._get_connection() as con:
                cur = con.cursor()
                cur.execute(sql, params)
                rows = cur.fetchall()
                for row in rows:
                    entry = self._row_to_entry(row)
                    raw_rank = float(row["rank"]) if "rank" in row.keys() else 0.0
                    # Lower bm25 rank value means higher relevance in sqlite3 FTS5
                    norm_score = max(0.1, 1.0 / (1.0 + abs(raw_rank)))
                    if entry.pinned:
                        norm_score += 0.5
                    is_stale = self.check_stale(entry)
                    results.append(
                        MemorySearchResult(
                            entry=entry,
                            score=round(norm_score, 4),
                            match_reason="fts5_bm25",
                            is_stale=is_stale,
                        )
                    )
        except sqlite3.OperationalError:
            # Fallback to LIKE query if FTS query syntax encounters unexpected issue
            fallback_sql = f"""
                SELECT * FROM memory_entries e
                WHERE (e.title LIKE ? OR e.content LIKE ? OR e.category LIKE ?)
                {layer_filter.replace('AND e.', 'AND ')}
                ORDER BY pinned DESC, updated_at DESC
                LIMIT ?;
            """
            like_pat = f"%{sanitized_terms[0]}%"
            like_params: list[Any] = [like_pat, like_pat, like_pat]
            if layer:
                like_params.append(layer_val)
            if status:
                like_params.append(status_val)
            like_params.append(limit)

            with self._get_connection() as con:
                cur = con.cursor()
                cur.execute(fallback_sql, like_params)
                for row in cur.fetchall():
                    entry = self._row_to_entry(row)
                    is_stale = self.check_stale(entry)
                    results.append(
                        MemorySearchResult(
                            entry=entry,
                            score=0.5,
                            match_reason="like_fallback",
                            is_stale=is_stale,
                        )
                    )

        return results

    def check_stale(self, entry: MemoryEntry) -> bool:
        """Determine if a memory entry references files that have been deleted from disk."""
        files = entry.metadata.get("files", [])
        if not files or not isinstance(files, list):
            return False

        for f in files:
            p = Path(f)
            file_path = p if p.is_absolute() else (self.workspace_root / p)
            if not file_path.exists():
                return True
        return False

    def clear(self, layer: MemoryLayer | str | None = None) -> int:
        """Purge memory records, optionally filtered by layer."""
        with self._get_connection() as con:
            cur = con.cursor()
            if layer:
                layer_val = layer.value if isinstance(layer, MemoryLayer) else str(layer)
                cur.execute("DELETE FROM memory_entries WHERE layer = ?", (layer_val,))
            else:
                cur.execute("DELETE FROM memory_entries;")
            count = cur.rowcount
            con.commit()
            return count

    def get_stats(self) -> MemoryStats:
        """Calculate summary statistics for persistent memory store."""
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM memory_entries")
            total = cur.fetchone()[0]

            cur.execute("SELECT layer, COUNT(*) FROM memory_entries GROUP BY layer")
            by_layer = {row[0]: row[1] for row in cur.fetchall()}

            cur.execute("SELECT status, COUNT(*) FROM memory_entries GROUP BY status")
            by_status = {row[0]: row[1] for row in cur.fetchall()}

            cur.execute("SELECT MAX(updated_at) FROM memory_entries")
            last_updated = cur.fetchone()[0]

            cur.execute("SELECT MAX(version) FROM schema_version")
            schema_ver = cur.fetchone()[0] or CURRENT_SCHEMA_VERSION

        file_size = self.db_path.stat().st_size if self.db_path.exists() else 0

        return MemoryStats(
            total_entries=total,
            by_layer=by_layer,
            by_status=by_status,
            db_size_bytes=file_size,
            db_path=str(self.db_path),
            schema_version=schema_ver,
            last_updated=last_updated,
        )

    def rebuild_from_project(self, project_summary: ProjectSummary) -> int:
        """Re-scan project summary and refresh Layer A (Project Memory) baseline records."""
        now_str = datetime.now(timezone.utc).isoformat()
        records_written = 0

        # 1. Project Identity & Purpose
        purpose_content = (
            f"Project Type: {project_summary.project_type}\n"
            f"Workspace Root: {project_summary.workspace_root}\n"
        )
        if project_summary.has_readme and project_summary.readme_excerpt:
            purpose_content += f"\nREADME Overview:\n{project_summary.readme_excerpt[:1000]}"

        self.add_entry(
            MemoryEntry(
                id="mem_proj_identity",
                layer=MemoryLayer.PROJECT,
                category="purpose",
                title="Project Purpose & Identity",
                content=purpose_content,
                source="auto_discovery",
                pinned=True,
                updated_at=now_str,
            )
        )
        records_written += 1

        # 2. Technology Stack & Manifests
        stack_content = f"Manifest Files: {', '.join(project_summary.manifest_files) or 'None'}\n"
        stack_content += f"Core Technology: {project_summary.project_type}\n"
        self.add_entry(
            MemoryEntry(
                id="mem_proj_stack",
                layer=MemoryLayer.PROJECT,
                category="stack",
                title="Technology Stack & Manifests",
                content=stack_content,
                metadata={"manifests": project_summary.manifest_files},
                source="auto_discovery",
                pinned=True,
                updated_at=now_str,
            )
        )
        records_written += 1

        # 3. Verified Build & Test Command
        if project_summary.suggested_test_command:
            self.add_entry(
                MemoryEntry(
                    id="mem_proj_test_cmd",
                    layer=MemoryLayer.PROJECT,
                    category="test_command",
                    title="Verified Build and Test Command",
                    content=f"Primary test verification command: {project_summary.suggested_test_command}",
                    metadata={"command": project_summary.suggested_test_command},
                    source="auto_discovery",
                    pinned=True,
                    updated_at=now_str,
                )
            )
            records_written += 1

        # 4. Directory Structure & Key Modules
        if project_summary.file_tree_summary:
            self.add_entry(
                MemoryEntry(
                    id="mem_proj_structure",
                    layer=MemoryLayer.PROJECT,
                    category="structure",
                    title="Directory Structure & Module Layout",
                    content=project_summary.file_tree_summary[:2000],
                    source="auto_discovery",
                    pinned=False,
                    updated_at=now_str,
                )
            )
            records_written += 1

        return records_written

    # --- Backward compatibility methods with legacy ProjectMemory ---
    def set_fact(self, key: str, value: str) -> None:
        """Legacy helper to store key-value facts in Layer A."""
        fact_id = f"fact_{uuid.uuid5(uuid.NAMESPACE_DNS, key).hex[:8]}"
        self.add_entry(
            MemoryEntry(
                id=fact_id,
                layer=MemoryLayer.PROJECT,
                category="fact",
                title=key,
                content=value,
                source="legacy_fact",
            )
        )

    def get_fact(self, key: str) -> str | None:
        """Legacy helper to retrieve a fact by key."""
        fact_id = f"fact_{uuid.uuid5(uuid.NAMESPACE_DNS, key).hex[:8]}"
        entry = self.get_entry(fact_id)
        if entry:
            return entry.content
        # Fallback search by title
        matches = self.search(key, layer=MemoryLayer.PROJECT, limit=1)
        for m in matches:
            if m.entry.category == "fact" and m.entry.title == key:
                return m.entry.content
        return None

    def list_facts(self) -> dict[str, str]:
        """Legacy helper to list all stored facts as key-value pairs."""
        entries = self.list_entries(layer=MemoryLayer.PROJECT, limit=500)
        return {e.title: e.content for e in entries if e.category == "fact"}


# Backward-compatible alias
ProjectMemory = SQLiteProjectMemory
