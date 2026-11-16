"""Catalogue and discovery registry for available connectors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from codemind.connectors.models import ConnectorManifest

if TYPE_CHECKING:
    from codemind.connectors.base import ConnectorAdapter


class ConnectorRegistry:
    """Central registry and catalogue of all available application connectors."""

    def __init__(self) -> None:
        self._adapters: dict[str, type[ConnectorAdapter]] = {}

    def register(self, adapter_cls: type[ConnectorAdapter]) -> None:
        """Register a connector adapter class into the catalogue."""
        cid = adapter_cls.manifest.connector_id
        self._adapters[cid] = adapter_cls

    def get(self, connector_id: str) -> type[ConnectorAdapter] | None:
        """Retrieve an adapter class by its connector ID."""
        return self._adapters.get(connector_id)

    def list_connectors(self) -> list[ConnectorManifest]:
        """List manifests for all registered connectors."""
        return [cls.manifest for cls in self._adapters.values()]

    def search_connectors(self, query: str) -> list[ConnectorManifest]:
        """Search connector catalogue by name, description, or category."""
        return self.search(query)

    def search(self, query: str) -> list[ConnectorManifest]:
        """Search connector catalogue by name, description, category, or action."""
        q = query.lower().strip()
        matches: list[ConnectorManifest] = []

        for cls in self._adapters.values():
            m = cls.manifest
            if (
                q in m.connector_id.lower()
                or q in m.name.lower()
                or q in m.description.lower()
                or q in m.category.lower()
                or any(q in a.name.lower() or q in a.description.lower() for a in m.actions)
            ):
                matches.append(m)
        return matches

    def get_manifest(self, connector_id: str) -> ConnectorManifest | None:
        """Retrieve manifest for a specific connector."""
        cls = self.get(connector_id)
        return cls.manifest if cls else None
