"""Ollama native adapter for CodeMind CLI."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from codemind.models.base import (
    ChatMessage,
    HealthStatus,
    ModelAdapter,
    ModelCapabilityProfile,
    ModelResponse,
    ModelTimeoutError,
    ModelUnavailableError,
    ModelUsage,
)


class OllamaAdapter(ModelAdapter):
    """Direct adapter for Ollama REST API (/api/chat, /api/tags)."""

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:11434",
        model_name: str = "qwen3.6:35b",
        timeout_seconds: int = 120,
        options: dict[str, Any] | None = None,
    ):
        super().__init__(
            endpoint=endpoint,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            options=options,
        )
        self._capabilities = ModelCapabilityProfile(
            supports_streaming=True,
            supports_structured_output=True,
            supports_system_messages=True,
            context_window=32768,
        )

    @property
    def capability_profile(self) -> ModelCapabilityProfile:
        return self._capabilities

    async def list_models(self) -> list[dict[str, Any]]:
        """Query /api/tags to list all installed Ollama models with metadata."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.endpoint}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = []
                    for m in data.get("models", []):
                        models.append({
                            "name": m.get("name"),
                            "provider": "ollama",
                            "size_bytes": m.get("size", 0),
                            "parameter_size": m.get("details", {}).get("parameter_size", "unknown"),
                            "quantization": m.get("details", {}).get("quantization_level", "unknown"),
                            "family": m.get("details", {}).get("family", "unknown"),
                            "modified_at": m.get("modified_at", ""),
                        })
                    return models
        except Exception:
            pass
        return []

    async def check_health(self) -> HealthStatus:
        """Query /api/tags to verify Ollama status and target model presence."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.endpoint}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("name") for m in data.get("models", [])]
                    model_found = self.model_name in models or any(self.model_name in m for m in models)
                    return HealthStatus(
                        healthy=True,
                        details={
                            "endpoint": self.endpoint,
                            "models_installed": models,
                            "target_model_present": model_found,
                            "message": "Ready" if model_found else f"Model '{self.model_name}' not loaded in Ollama",
                        },
                    )
                return HealthStatus(healthy=False, error=f"Ollama returned HTTP {resp.status_code}")
        except Exception as ex:
            return HealthStatus(healthy=False, error=f"Failed to connect to Ollama at {self.endpoint}: {ex}")

    async def generate(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        """Call Ollama /api/chat with stream: false."""
        chat_options: dict[str, Any] = {
            "temperature": temperature,
            "num_predict": max_tokens or 4096,
        }
        if self.options:
            chat_options.update(self.options)

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": chat_options,
        }

        url = f"{self.endpoint}/api/chat"
        try:
            async with httpx.AsyncClient(timeout=float(self.timeout_seconds)) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    raise ModelUnavailableError(f"Ollama error HTTP {resp.status_code}: {resp.text}")
                data = resp.json()
                msg = data.get("message", {})
                content = msg.get("content", "")

                # If content is empty but model emitted thinking, check if json is inside thinking
                if not content and "thinking" in msg:
                    content = msg["thinking"]

                prompt_tokens = data.get("prompt_eval_count", 0)
                completion_tokens = data.get("eval_count", 0)
                usage = ModelUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                )

                return ModelResponse(
                    content=content,
                    usage=usage,
                    finish_reason="stop",
                    raw_response=data,
                )
        except httpx.TimeoutException as ex:
            raise ModelTimeoutError(f"Ollama request timed out after {self.timeout_seconds}s: {ex}")
        except httpx.ConnectError as ex:
            raise ModelUnavailableError(f"Could not reach Ollama at {self.endpoint}: {ex}")

    async def generate_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream chunks from Ollama /api/chat."""
        chat_options: dict[str, Any] = {
            "temperature": temperature,
            "num_predict": max_tokens or 4096,
        }
        if self.options:
            chat_options.update(self.options)

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": chat_options,
        }

        url = f"{self.endpoint}/api/chat"
        try:
            async with httpx.AsyncClient(timeout=float(self.timeout_seconds)) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    if resp.status_code != 200:
                        raise ModelUnavailableError(f"Ollama stream error HTTP {resp.status_code}")
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            chunk = obj.get("message", {}).get("content", "")
                            if chunk:
                                yield chunk
                        except json.JSONDecodeError:
                            continue
        except httpx.TimeoutException as ex:
            raise ModelTimeoutError(f"Ollama streaming timed out: {ex}")
        except httpx.ConnectError as ex:
            raise ModelUnavailableError(f"Ollama connection error at {self.endpoint}: {ex}")
