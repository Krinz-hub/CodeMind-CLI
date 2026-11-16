"""Mock model adapter for hermetic, deterministic testing."""

from __future__ import annotations

from typing import Any, AsyncIterator, Callable

from codemind.models.base import (
    ChatMessage,
    HealthStatus,
    ModelAdapter,
    ModelCapabilityProfile,
    ModelResponse,
    ModelUsage,
)


class MockModelAdapter(ModelAdapter):
    """Deterministic mock adapter for automated tests without a running LLM."""

    def __init__(
        self,
        endpoint: str = "mock://local",
        model_name: str = "mock-codemind",
        responses: list[str] | None = None,
        response_generator: Callable[[list[ChatMessage]], str] | None = None,
        options: dict[str, Any] | None = None,
    ):
        super().__init__(
            endpoint=endpoint,
            model_name=model_name,
            options=options,
        )
        self.responses: list[str] = list(responses or [])
        self.response_generator = response_generator
        self.history_calls: list[list[ChatMessage]] = []
        self._capabilities = ModelCapabilityProfile(
            supports_streaming=True,
            supports_structured_output=True,
            supports_json_schema=True,
            supports_tool_calling=True,
            supports_system_messages=True,
            supports_cancellation=True,
            supports_usage_reporting=True,
            context_window=65536,
            is_mock=True,
            is_local=True,
        )

    @property
    def capability_profile(self) -> ModelCapabilityProfile:
        return self._capabilities

    async def list_models(self) -> list[dict[str, Any]]:
        return [
            {"name": "mock-codemind", "provider": "mock", "parameter_size": "0M", "family": "mock"},
            {"name": "mock-qwen", "provider": "mock", "parameter_size": "0M", "family": "mock"},
        ]

    async def check_health(self) -> HealthStatus:
        return HealthStatus(
            healthy=True,
            details={"mode": "mock", "queued_responses": len(self.responses), "message": "Ready"},
        )

    def queue_response(self, text: str) -> None:
        """Add a response to the queue."""
        self.responses.append(text)

    async def generate(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        self.history_calls.append(list(messages))
        if self.response_generator:
            content = self.response_generator(messages)
        elif self.responses:
            content = self.responses.pop(0)
        else:
            # Default envelope
            content = '{"protocol_version": "1", "type": "final", "content": "Mock completed."}'

        return ModelResponse(
            content=content,
            usage=ModelUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
            finish_reason="stop",
        )

    async def generate_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        resp = await self.generate(messages, temperature=temperature, max_tokens=max_tokens)
        # Yield in two chunks
        mid = len(resp.content) // 2
        yield resp.content[:mid]
        yield resp.content[mid:]
