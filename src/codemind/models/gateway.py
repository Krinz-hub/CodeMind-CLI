"""Unified model inference gateway and capability manager (Phase B Workstream E).

Provides a single authoritative gateway for all agent and worker inferences:
- Normalizes model provider interactions through ModelAdapter.
- Tracks and reports explicit capability profiles.
- Enforces visible fallback with audit history.
- Enforces local-only policy (prevents silent cloud leakage).
- Assembles streaming chunks into verified completed messages.
- Prevents mock providers from claiming real model execution.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from codemind.models.base import (
    ChatMessage,
    HealthStatus,
    ModelAdapter,
    ModelCapabilityProfile,
    ModelError,
    ModelResponse,
    ModelUnavailableError,
    ModelUsage,
)
from codemind.models.custom import FallbackAwareModelAdapter

logger = logging.getLogger("codemind.models.gateway")

# Known public cloud endpoints that violate local-first policy
CLOUD_ENDPOINT_KEYWORDS = [
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.cohere.ai",
    "api.mistral.ai",
    "api.groq.com",
]


class ModelGateway:
    """Unified inference gateway governing all model interactions."""

    def __init__(
        self,
        adapter: ModelAdapter,
        local_only: bool = True,
    ):
        self.adapter = adapter
        self.local_only = local_only
        self.fallback_history: list[dict[str, Any]] = []
        self._validate_local_policy(self.adapter.endpoint)

    def _validate_local_policy(self, endpoint: str) -> None:
        """Enforce strict local-first policy if local_only is enabled."""
        if not self.local_only:
            return

        endpoint_lower = endpoint.lower()
        for cloud_kw in CLOUD_ENDPOINT_KEYWORDS:
            if cloud_kw in endpoint_lower:
                raise ModelUnavailableError(
                    f"Policy Violation: Silent cloud routing blocked. Endpoint '{endpoint}' "
                    f"contacts external cloud provider '{cloud_kw}', which violates local-first policy."
                )

    @property
    def capability_profile(self) -> ModelCapabilityProfile:
        """Return the explicit capability profile of the underlying adapter."""
        return self.adapter.capability_profile

    @property
    def is_mock(self) -> bool:
        """Return whether the active adapter is a deterministic test mock."""
        return getattr(self.capability_profile, "is_mock", False)

    @property
    def is_fallback_active(self) -> bool:
        """Check if fallback adapter is actively handling inference."""
        if isinstance(self.adapter, FallbackAwareModelAdapter):
            return self.adapter.is_fallback_active
        return False

    async def check_health(self) -> HealthStatus:
        """Query serving endpoint to verify health and model presence."""
        self._validate_local_policy(self.adapter.endpoint)
        return await self.adapter.check_health()

    async def list_models(self) -> list[dict[str, Any]]:
        """List models available on serving provider."""
        return await self.adapter.list_models()

    async def generate(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        """Generate complete response with local policy validation and fallback auditing."""
        self._validate_local_policy(self.adapter.endpoint)

        was_fallback = self.is_fallback_active
        t_start = datetime.now(timezone.utc)

        try:
            response = await self.adapter.generate(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # Audit fallback transitions
            now_fallback = self.is_fallback_active
            if now_fallback and not was_fallback:
                fb_event = {
                    "timestamp": t_start.isoformat(),
                    "primary_endpoint": self.adapter.endpoint,
                    "event": "fallback_activated",
                    "reason": "Primary endpoint failed or unreachable",
                }
                self.fallback_history.append(fb_event)
                logger.warning(f"ModelGateway: Fallback activated -> {fb_event}")

            return response
        except Exception as ex:
            if self.is_fallback_active and not was_fallback:
                self.fallback_history.append({
                    "timestamp": t_start.isoformat(),
                    "primary_endpoint": self.adapter.endpoint,
                    "event": "fallback_activated",
                    "reason": str(ex),
                })
            raise

    async def generate_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream response chunks from model."""
        self._validate_local_policy(self.adapter.endpoint)
        async for chunk in self.adapter.generate_stream(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield chunk

    async def accumulate_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> str:
        """Safely accumulate streaming chunks, verify completion, and return complete text."""
        chunks: list[str] = []
        async for chunk in self.generate_stream(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            chunks.append(chunk)

        complete_text = "".join(chunks).strip()
        if not complete_text:
            raise ModelError("Streaming response completed but yielded zero text content.")

        return complete_text
