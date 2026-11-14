"""Model adapter base abstractions and data transfer objects."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from pydantic import BaseModel, Field


class ModelCapabilityProfile(BaseModel):
    supports_streaming: bool = True
    supports_structured_output: bool = True
    supports_system_messages: bool = True
    context_window: int = 32768
    supports_multiple_tool_calls: bool = False


class HealthStatus(BaseModel):
    healthy: bool
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ModelUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatMessage(BaseModel):
    role: str  # "system", "user", "assistant", "tool"
    content: str
    name: str | None = None


class ModelResponse(BaseModel):
    content: str
    usage: ModelUsage | None = None
    finish_reason: str = "stop"
    raw_response: dict[str, Any] | None = None


class ModelError(Exception):
    """Base exception for model layer errors."""


class ModelUnavailableError(ModelError):
    """Raised when the target model server cannot be reached."""


class ModelTimeoutError(ModelError):
    """Raised when model inference times out."""


class ContextOverflowError(ModelError):
    """Raised when the context length exceeds model context window."""


class MalformedResponseError(ModelError):
    """Raised when the model output cannot be parsed into an envelope."""


class ModelAdapter(ABC):
    """Abstract interface defining the contract for model serving adapters."""

    def __init__(
        self,
        endpoint: str,
        model_name: str,
        timeout_seconds: int = 120,
        options: dict[str, Any] | None = None,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.options = options or {}

    @property
    @abstractmethod
    def capability_profile(self) -> ModelCapabilityProfile:
        """Return the explicit capability profile of this adapter."""
        pass

    @abstractmethod
    async def check_health(self) -> HealthStatus:
        """Verify endpoint connectivity and model availability."""
        pass

    @abstractmethod
    async def list_models(self) -> list[dict[str, Any]]:
        """Query serving endpoint to discover available models."""
        pass

    @abstractmethod
    async def generate(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        """Generate complete response from model."""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream generated text chunks from model."""
        pass
