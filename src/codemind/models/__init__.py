"""Model subsystem exports and factory function."""

from __future__ import annotations

from codemind.config import ModelProvider, ModelSettings
from codemind.models.base import (
    ChatMessage,
    ContextOverflowError,
    HealthStatus,
    MalformedResponseError,
    ModelAdapter,
    ModelCapabilityProfile,
    ModelError,
    ModelResponse,
    ModelTimeoutError,
    ModelUnavailableError,
    ModelUsage,
)
from codemind.models.codemind_local import CodeMindLocalAdapter
from codemind.models.mock import MockModelAdapter
from codemind.models.ollama import OllamaAdapter
from codemind.models.protocol import (
    CURRENT_PROTOCOL_VERSION,
    ActionType,
    FinalAction,
    MalformedAction,
    ParsedAction,
    PlanAction,
    ProtocolParser,
    TaskPlanItem,
    ToolCallAction,
)


def create_adapter(settings: ModelSettings) -> ModelAdapter:
    """Instantiate appropriate adapter from ModelSettings."""
    if settings.provider == ModelProvider.OLLAMA:
        return OllamaAdapter(
            endpoint=settings.endpoint,
            model_name=settings.model_name,
            timeout_seconds=settings.timeout_seconds,
            options=settings.options,
        )
    elif settings.provider == ModelProvider.MOCK:
        return MockModelAdapter(
            endpoint=settings.endpoint,
            model_name=settings.model_name,
            options=settings.options,
        )
    elif settings.provider in (ModelProvider.OPENAI_LOCAL, ModelProvider.CODEMIND_LOCAL):
        return CodeMindLocalAdapter(
            endpoint=settings.endpoint,
            model_name=settings.model_name,
            timeout_seconds=settings.timeout_seconds,
            options=settings.options,
        )
    else:
        # Default fallback
        return CodeMindLocalAdapter(
            endpoint=settings.endpoint,
            model_name=settings.model_name,
            timeout_seconds=settings.timeout_seconds,
            options=settings.options,
        )


__all__ = [
    "ModelAdapter",
    "ModelCapabilityProfile",
    "HealthStatus",
    "ModelUsage",
    "ChatMessage",
    "ModelResponse",
    "ModelError",
    "ModelUnavailableError",
    "ModelTimeoutError",
    "ContextOverflowError",
    "MalformedResponseError",
    "CodeMindLocalAdapter",
    "OllamaAdapter",
    "MockModelAdapter",
    "ProtocolParser",
    "CURRENT_PROTOCOL_VERSION",
    "ActionType",
    "ToolCallAction",
    "PlanAction",
    "FinalAction",
    "MalformedAction",
    "ParsedAction",
    "TaskPlanItem",
    "create_adapter",
]
