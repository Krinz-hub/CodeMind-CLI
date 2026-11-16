"""Unit tests for the SQLite-backed persistent project memory engine."""

import os
from pathlib import Path

from codemind.context.discovery import ProjectDiscovery
from codemind.memory.distiller import MemoryDistiller
from codemind.memory.models import (
    MemoryEntry,
    MemoryLayer,
    MemoryStatus,
)
from codemind.memory.retriever import MemoryRetriever
from codemind.memory.store import SQLiteProjectMemory
from codemind.planning.task import TaskPlan
from codemind.runtime.state import AgentState
from codemind.verification.reporter import HonestCompletionReport
from codemind.verification.runner import TestCheckResult
from tests.base import BaseAgentTestCase


class TestProjectMemory(BaseAgentTestCase):
    """Test suite for SQLiteProjectMemory, FTS5 indexing, retriever, and distiller."""

    def setUp(self) -> None:
        super().setUp()
        self.memory = SQLiteProjectMemory(self.workspace_root)

    def test_sqlite_memory_init_and_schema(self) -> None:
        """Verify database initialization, schema version, and FTS5 tables."""
        self.assertTrue(self.memory.db_path.exists())
        stats = self.memory.get_stats()
        self.assertEqual(stats.schema_version, 1)
        self.assertEqual(stats.total_entries, 0)

    def test_crud_operations(self) -> None:
        """Verify full lifecycle: create, read, update, list, and delete."""
        entry = MemoryEntry(
            id="mem_dec_test1",
            layer=MemoryLayer.DECISION,
            category="adr",
            title="Use SQLite for Memory",
            content="SQLite with FTS5 provides local-first ACID search without cloud overhead.",
            metadata={"trade_offs": "No distributed clustering"},
            pinned=True,
        )
        saved = self.memory.add_entry(entry)
        self.assertEqual(saved.id, "mem_dec_test1")

        # Get
        retrieved = self.memory.get_entry("mem_dec_test1")
        self.assertIsNotNone(retrieved)
        assert retrieved is not None
        self.assertEqual(retrieved.title, "Use SQLite for Memory")
        self.assertTrue(retrieved.pinned)

        # Update
        updated = self.memory.update_entry(
            "mem_dec_test1",
            content="Updated content for SQLite decision.",
            status=MemoryStatus.SUPERSEDED,
            pinned=False,
        )
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated.content, "Updated content for SQLite decision.")
        self.assertEqual(updated.status, MemoryStatus.SUPERSEDED)
        self.assertFalse(updated.pinned)

        # List
        all_entries = self.memory.list_entries(layer=MemoryLayer.DECISION)
        self.assertEqual(len(all_entries), 1)

        # Delete
        deleted = self.memory.delete_entry("mem_dec_test1")
        self.assertTrue(deleted)
        self.assertIsNone(self.memory.get_entry("mem_dec_test1"))

    def test_secret_redaction_gate(self) -> None:
        """Verify secrets are redacted before persistence in SQLite and FTS."""
        leaky_entry = MemoryEntry(
            id="mem_leak_01",
            layer=MemoryLayer.TASK,
            category="defect",
            title="Fix API key in headers with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            content="Secret key was sk-123456789012345678901234567890 and token was ghp_123456789012345678901234567890123456",
            metadata={"token": "ghp_123456789012345678901234567890123456"},
        )
        saved = self.memory.add_entry(leaky_entry)

        self.assertNotIn("sk-123456789012345678901234567890", saved.content)
        self.assertIn("[REDACTED_OPENAI_KEY]", saved.content)
        self.assertNotIn("ghp_123456789012345678901234567890123456", saved.content)
        self.assertIn("[REDACTED_GITHUB_TOKEN]", saved.content)
        self.assertIn("[REDACTED_TOKEN]", saved.title)

        # Verify raw database contents do not contain secrets
        with self.memory._get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT content, title, metadata_json FROM memory_entries WHERE id = 'mem_leak_01'")
            row = cur.fetchone()
            self.assertNotIn("ghp_1234567890", row[0])
            self.assertNotIn("sk-1234567890", row[0])
            self.assertNotIn("ghp_1234567890", row[2])

    def test_fts5_bm25_search_and_ranking(self) -> None:
        """Verify FTS5 full-text indexing, BM25 ranking, and queries."""
        self.memory.add_entry(
            MemoryEntry(
                id="mem_1",
                layer=MemoryLayer.DECISION,
                category="database",
                title="Adopt PostgreSQL for relational storage",
                content="PostgreSQL was selected for its relational consistency and JSONB support.",
            )
        )
        self.memory.add_entry(
            MemoryEntry(
                id="mem_2",
                layer=MemoryLayer.DECISION,
                category="caching",
                title="Adopt Redis for in-memory session cache",
                content="Redis provides sub-millisecond key-value lookups for active user sessions.",
            )
        )
        self.memory.add_entry(
            MemoryEntry(
                id="mem_3",
                layer=MemoryLayer.TASK,
                category="feature",
                title="Added PostgreSQL migration runner",
                content="Implemented alembic migration runner for PostgreSQL schemas.",
            )
        )

        # Search for PostgreSQL
        pg_results = self.memory.search("PostgreSQL")
        self.assertEqual(len(pg_results), 2)
        matched_ids = [r.entry.id for r in pg_results]
        self.assertIn("mem_1", matched_ids)
        self.assertIn("mem_3", matched_ids)

        # Search for Redis
        redis_results = self.memory.search("Redis session cache")
        self.assertEqual(len(redis_results), 1)
        self.assertEqual(redis_results[0].entry.id, "mem_2")

    def test_stale_memory_detection(self) -> None:
        """Verify staleness detection when referenced files are absent from disk."""
        # Create a real file
        self.create_file("src/app.py", "def run(): pass\n")

        valid_entry = MemoryEntry(
            id="mem_valid",
            layer=MemoryLayer.TASK,
            category="feature",
            title="App runner implementation",
            content="Created app runner in src/app.py",
            metadata={"files": ["src/app.py"]},
        )
        self.memory.add_entry(valid_entry)
        self.assertFalse(self.memory.check_stale(valid_entry))

        stale_entry = MemoryEntry(
            id="mem_stale",
            layer=MemoryLayer.TASK,
            category="feature",
            title="Deleted helper module",
            content="Created helper in src/deleted.py",
            metadata={"files": ["src/deleted.py"]},
        )
        self.memory.add_entry(stale_entry)
        self.assertTrue(self.memory.check_stale(stale_entry))

    def test_legacy_backward_compatibility(self) -> None:
        """Verify set_fact, get_fact, and list_facts legacy helpers."""
        self.memory.set_fact("author", "DeepMind Team")
        self.memory.set_fact("language", "Python")

        self.assertEqual(self.memory.get_fact("author"), "DeepMind Team")
        self.assertEqual(self.memory.get_fact("language"), "Python")
        self.assertIsNone(self.memory.get_fact("nonexistent"))

        facts = self.memory.list_facts()
        self.assertEqual(facts.get("author"), "DeepMind Team")
        self.assertEqual(facts.get("language"), "Python")

    def test_memory_retriever_context_budget(self) -> None:
        """Verify multi-tier context retrieval and bounded output formatting."""
        # Add Layer A
        self.memory.add_entry(
            MemoryEntry(
                id="mem_proj_core",
                layer=MemoryLayer.PROJECT,
                category="stack",
                title="Core Stack",
                content="Python 3.12, Typer CLI, SQLite 3",
                pinned=True,
            )
        )
        # Add Layer D
        self.memory.add_entry(
            MemoryEntry(
                id="mem_inst_rule",
                layer=MemoryLayer.INSTRUCTION,
                category="style_rule",
                title="Style Rule",
                content="Always use standard library dataclasses rather than Pydantic in core models.",
                pinned=True,
            )
        )
        # Add Layer B
        self.memory.add_entry(
            MemoryEntry(
                id="mem_dec_auth",
                layer=MemoryLayer.DECISION,
                category="adr",
                title="Authentication Mechanism",
                content="JWT tokens with ed25519 signatures.",
                metadata={"rejected_alternatives": "Session cookies"},
            )
        )

        retriever = MemoryRetriever(self.memory, max_budget_chars=4000)
        context = retriever.retrieve_context(instruction="Implement token authentication handler")

        self.assertIn("Workspace Guidelines & Directives (Layer D)", context)
        self.assertIn("Always use standard library dataclasses", context)
        self.assertIn("Persistent Project Knowledge (Layer A)", context)
        self.assertIn("Core Stack", context)
        self.assertIn("Architectural Decisions & Rationale (Layer B)", context)
        self.assertIn("Authentication Mechanism", context)
        self.assertIn("Rejected: Session cookies", context)
        self.assertLessEqual(len(context), 4000)

    def test_memory_distiller(self) -> None:
        """Verify post-task distillation of accomplishments and user directives."""
        distiller = MemoryDistiller(self.memory)

        # 1. Distill verified bugfix
        state = AgentState(
            session_id="test_sess",
            workspace_root=str(self.workspace_root),
            task_instruction="Fix null pointer exception in user auth router",
            turn_count=3,
            files_modified=["src/auth.py"],
            final_summary=["Guarded None check on user payload"],
        )
        report = HonestCompletionReport(
            files_modified=["src/auth.py"],
            verified=True,
            checks=[TestCheckResult(command="pytest tests/test_auth.py", passed=True, exit_code=0, stdout="1 passed")],
        )

        created = distiller.distill(state=state, report=report)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].layer, MemoryLayer.TASK)
        self.assertEqual(created[0].category, "bugfix")
        self.assertIn("src/auth.py", created[0].metadata["files"])

        # 2. Distill persistent directive
        directive_state = AgentState(
            session_id="test_sess2",
            workspace_root=str(self.workspace_root),
            task_instruction="Always prefer pure functions without global state in utils",
            turn_count=1,
        )
        empty_report = HonestCompletionReport(verified=True)
        directive_created = distiller.distill(state=directive_state, report=empty_report)
        self.assertEqual(len(directive_created), 1)
        self.assertEqual(directive_created[0].layer, MemoryLayer.INSTRUCTION)
        self.assertTrue(directive_created[0].pinned)

    def test_cross_project_isolation(self) -> None:
        """Verify that two distinct workspaces maintain completely isolated memories."""
        other_dir = Path(self.temp_dir) / "other_project"
        other_dir.mkdir(parents=True, exist_ok=True)
        other_memory = SQLiteProjectMemory(other_dir)

        # Write to self.memory
        self.memory.add_entry(
            MemoryEntry(
                id="mem_p1",
                layer=MemoryLayer.PROJECT,
                category="identity",
                title="Project 1 Alpha",
                content="This is Project 1.",
            )
        )

        # Write to other_memory
        other_memory.add_entry(
            MemoryEntry(
                id="mem_p2",
                layer=MemoryLayer.PROJECT,
                category="identity",
                title="Project 2 Beta",
                content="This is Project 2.",
            )
        )

        # Verify Project 1 does not see Project 2
        self.assertIsNotNone(self.memory.get_entry("mem_p1"))
        self.assertIsNone(self.memory.get_entry("mem_p2"))

        # Verify Project 2 does not see Project 1
        self.assertIsNotNone(other_memory.get_entry("mem_p2"))
        self.assertIsNone(other_memory.get_entry("mem_p1"))
