"""Automatic discovery of local inference services and installed models."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codemind.config import CodeMindConfig, ModelProvider, ModelSettings
from codemind.models.base import ModelAdapter
from codemind.models.codemind_local import CodeMindLocalAdapter
from codemind.models.ollama import OllamaAdapter


class DiscoveredModel(BaseModel):
    name: str
    provider: str
    endpoint: str
    status: str = "Available"
    size_gb: float | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    family: str | None = None
    is_active: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ModelDiscovery:
    """Probes local endpoints to identify installed models and active providers."""

    DEFAULT_PROBE_ENDPOINTS = [
        {"provider": "ollama", "endpoint": "http://127.0.0.1:11434"},
        {"provider": "openai-local", "endpoint": "http://127.0.0.1:11434/v1"},
        {"provider": "codemind-local", "endpoint": "http://127.0.0.1:8000/v1"},
    ]

    @classmethod
    async def discover_all(cls, config: CodeMindConfig | None = None) -> list[DiscoveredModel]:
        """Scan all known local endpoints and configured endpoints."""
        discovered: list[DiscoveredModel] = []
        seen_keys: set[tuple[str, str]] = set()

        # Build list of endpoints to probe
        probe_list = list(cls.DEFAULT_PROBE_ENDPOINTS)
        if config and config.model:
            custom_entry = {
                "provider": config.model.provider.value,
                "endpoint": config.model.endpoint,
            }
            if custom_entry not in probe_list:
                probe_list.insert(0, custom_entry)

        active_model = config.model.model_name if config else ""
        active_provider = config.model.provider.value if config else ""

        for target in probe_list:
            provider = target["provider"]
            endpoint = target["endpoint"]

            try:
                models_found = await cls._probe_endpoint(provider, endpoint)
                for m in models_found:
                    key = (m["name"], provider)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    size_b = m.get("size_bytes")
                    size_gb = round(size_b / (1024**3), 1) if size_b else None

                    is_current = (
                        m["name"] == active_model
                        and (provider == active_provider or active_provider in ("openai-local", "codemind-local"))
                    )

                    discovered.append(
                        DiscoveredModel(
                            name=m["name"],
                            provider=provider,
                            endpoint=endpoint,
                            status="Available",
                            size_gb=size_gb,
                            parameter_size=m.get("parameter_size"),
                            quantization=m.get("quantization"),
                            family=m.get("family"),
                            is_active=is_current,
                            details=m,
                        )
                    )
            except Exception:
                continue

        return discovered

    @classmethod
    async def _probe_endpoint(cls, provider: str, endpoint: str) -> list[dict[str, Any]]:
        """Instantiate adapter and query model catalog."""
        if provider == "ollama":
            adapter = OllamaAdapter(endpoint=endpoint, model_name="")
            return await adapter.list_models()
        elif provider in ("openai-local", "codemind-local"):
            adapter = CodeMindLocalAdapter(endpoint=endpoint, model_name="")
            return await adapter.list_models()
        return []
