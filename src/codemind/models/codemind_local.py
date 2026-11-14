"""CodeMind local / OpenAI-compatible local adapter."""

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


class CodeMindLocalAdapter(ModelAdapter):
    """Communicates with OpenAI-compatible local model servers (vLLM, llama.cpp, SGLang, Ollama /v1)."""

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:8000/v1",
        model_name: str = "codemind",
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
        """Query /models or /v1/models endpoint."""
        url = f"{self.endpoint}/models"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    model_list = []
                    for item in data.get("data", []):
                        model_id = item.get("id") or item.get("name")
                        if model_id:
                            model_list.append({
                                "name": model_id,
                                "provider": "openai-local",
                                "details": item,
                            })
                    return model_list
        except Exception:
            pass
        return []

    async def check_health(self) -> HealthStatus:
        """Ping the model serving endpoint or query /models."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                url = f"{self.endpoint}/models"
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("id") for m in data.get("data", [])]
                    model_found = self.model_name in models if models else True
                    return HealthStatus(
                        healthy=True,
                        details={
                            "endpoint": self.endpoint,
                            "models": models,
                            "target_model_present": model_found,
                            "message": "Ready",
                        },
                    )
                # Fallback to health
                resp_alt = await client.get(self.endpoint.replace("/v1", "/health"))
                if resp_alt.status_code in (200, 404):
                    return HealthStatus(
                        healthy=True,
                        details={"endpoint": self.endpoint, "status_code": resp_alt.status_code, "message": "Ready"},
                    )
                return HealthStatus(
                    healthy=False,
                    error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )
        except httpx.ConnectError as err:
            return HealthStatus(healthy=False, error=f"Connection refused to {self.endpoint}: {err}")
        except Exception as ex:
            return HealthStatus(healthy=False, error=str(ex))

    async def generate(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        """Send chat completion request to OpenAI-compatible endpoint."""
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if self.options:
            for k, v in self.options.items():
                if k not in payload:
                    payload[k] = v

        url = f"{self.endpoint}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=float(self.timeout_seconds)) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    raise ModelUnavailableError(
                        f"Model server responded with HTTP {resp.status_code}: {resp.text}"
                    )
                data = resp.json()
                choice = data["choices"][0]
                message_obj = choice.get("message", {})
                content = message_obj.get("content") or ""
                # If content is empty but reasoning is present
                if not content and "reasoning" in message_obj:
                    content = message_obj["reasoning"]

                finish_reason = choice.get("finish_reason", "stop")

                usage = None
                if "usage" in data and data["usage"]:
                    u = data["usage"]
                    usage = ModelUsage(
                        prompt_tokens=u.get("prompt_tokens", 0),
                        completion_tokens=u.get("completion_tokens", 0),
                        total_tokens=u.get("total_tokens", 0),
                    )

                return ModelResponse(
                    content=content,
                    usage=usage,
                    finish_reason=finish_reason,
                    raw_response=data,
                )
        except httpx.TimeoutException as ex:
            raise ModelTimeoutError(f"Model generation timed out after {self.timeout_seconds}s: {ex}")
        except httpx.ConnectError as ex:
            raise ModelUnavailableError(f"Failed to connect to model endpoint at {self.endpoint}: {ex}")

    async def generate_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream SSE chunks from OpenAI-compatible endpoint."""
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        url = f"{self.endpoint}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=float(self.timeout_seconds)) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    if resp.status_code != 200:
                        raise ModelUnavailableError(
                            f"Model server streaming responded with HTTP {resp.status_code}"
                        )
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                        except json.JSONDecodeError:
                            continue
        except httpx.TimeoutException as ex:
            raise ModelTimeoutError(f"Streaming model request timed out: {ex}")
        except httpx.ConnectError as ex:
            raise ModelUnavailableError(f"Connection refused at {self.endpoint}: {ex}")
