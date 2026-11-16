"""Data models and enumerations for the persistent project memory system."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class MemoryLayer(str, Enum):
    """Semantic tier of persistent memory."""

    PROJECT = "project"          # Layer A: Project identity, tech stack, architecture, entry points
    DECISION = "decision"        # Layer B: Architectural decisions (ADRs), choices, trade-offs
    TASK = "task"                # Layer C: Completed features, bug fixes, unfinished tasks
    INSTRUCTION = "instruction"  # Layer D: Project-specific user preferences and constraints


class MemoryStatus(str, Enum):
    """Lifecycle status of a memory record."""

    ACTIVE = "active"            # Valid, current ground truth
    SUPERSEDED = "superseded"    # Replaced by a more recent decision/architecture change
    DEPRECATED = "deprecated"    # No longer applicable or valid


class MemoryEntry(BaseModel):
    """Structured record in persistent project memory."""

    id: str = Field(description="Unique identifier (e.g. mem_proj_1a2b3c)")
    layer: MemoryLayer = Field(description="Semantic memory layer (project, decision, task, instruction)")
    category: str = Field(description="Subcategory (e.g. architecture, stack, adr, bugfix, feature, style_rule)")
    title: str = Field(description="Brief title of the memory item")
    content: str = Field(description="Full text explanation or structured content")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata (files, dates, alternatives)")
    source: str = Field(default="agent", description="Origin of memory (auto_discovery, agent_task, user_instruction, manual)")
    status: MemoryStatus = Field(default=MemoryStatus.ACTIVE, description="Lifecycle status")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="ISO 8601 creation time")
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="ISO 8601 update time")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")
    pinned: bool = Field(default=False, description="Whether record is pinned to always appear in context")


class MemorySearchResult(BaseModel):
    """Result from full-text search and relevance ranking."""

    entry: MemoryEntry
    score: float = Field(ge=0.0, description="Relevance and rank score")
    match_reason: str = Field(default="", description="Reason for match (e.g. FTS5 BM25 match, pinned, identity)")
    is_stale: bool = Field(default=False, description="True if referenced files no longer exist on disk")


class MemoryStats(BaseModel):
    """Statistical overview of persistent project memory."""

    total_entries: int
    by_layer: dict[str, int]
    by_status: dict[str, int]
    db_size_bytes: int
    db_path: str
    schema_version: int
    last_updated: str | None = None
