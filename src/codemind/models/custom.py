"""Dedicated custom CodeMind foundation model adapter with fallback routing and protocol normalization."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx

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

logger = logging.getLogger("codemind.models.custom")


class ProtocolNormalizer:
    """Defensive parsing and normalization layer for model outputs into CodeMind v1 protocol."""

    @classmethod
    def normalize_response_content(cls, raw_content: str) -> str:
        """Sanitize raw completion text into a compliant JSON protocol string."""
        if not raw_content or not raw_content.strip():
            return json.dumps({
                "protocol_version": "1",
                "type": "malformed",
                "raw_content": "",
                "error": "Model emitted empty response.",
            })

        content = raw_content.strip()

        # 1. Strip reasoning / thinking tokens (e.g. <think>...</think>)
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        # 2. Extract JSON from markdown fences (```json ... ``` or ``` ... ```)
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if fence_match:
            candidate = fence_match.group(1).strip()
            try:
                data = json.loads(candidate)
                return cls._ensure_protocol_envelope(data, raw_content)
            except json.JSONDecodeError:
                pass

        # 3. Direct JSON parsing
        try:
            data = json.loads(content)
            return cls._ensure_protocol_envelope(data, raw_content)
        except json.JSONDecodeError:
            pass

        # 4. Search for outermost balanced JSON object in free-form text
        first_brace = content.find("{")
        last_brace = content.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            candidate = content[first_brace : last_brace + 1].strip()
            try:
                data = json.loads(candidate)
                return cls._ensure_protocol_envelope(data, raw_content)
            except json.JSONDecodeError:
                pass

        # 5. Non-JSON conversational text: Wrap safely into FinalAction rather than guessing tool call
        return json.dumps({
            "protocol_version": "1",
            "type": "final",
            "content": content,
            "summary": ["Synthesized response from model."],
        })

    @classmethod
    def _ensure_protocol_envelope(cls, data: dict[str, Any], raw_fallback: str) -> str:
        """Validate and patch JSON dictionary into valid v1 protocol envelope."""
        if not isinstance(data, dict):
            return json.dumps({
                "protocol_version": "1",
                "type": "final",
                "content": str(data),
            })

        # Inject protocol_version if omitted
        if "protocol_version" not in data or data["protocol_version"] != "1":
            data["protocol_version"] = "1"

        # Check action type
        action_type = data.get("type", "").lower()
        if action_type not in ("tool_call", "plan", "final", "malformed"):
            # If missing type but has 'tool', treat as tool_call
            if "tool" in data:
                data["type"] = "tool_call"
            elif "tasks" in data:
                data["type"] = "plan"
            elif "content" in data:
                data["type"] = "final"
            else:
                data["type"] = "final"
                data["content"] = str(data)

        # Sanitize tool_call arguments
        if data["type"] == "tool_call":
            if "arguments" not in data or not isinstance(data["arguments"], dict):
                data["arguments"] = {}
            if "reason" not in data or not data["reason"]:
                data["reason"] = f"Invoke {data.get('tool', 'tool')}"

        # Sanitize final
        if data["type"] == "final":
            if "content" not in data:
                data["content"] = ""
            if "summary" not in data:
                data["summary"] = []

        return json.dumps(data)


class CodeMindCustomAdapter(ModelAdapter):
    """Dedicated model adapter for the proprietary CodeMind foundation model.

    Connects to local OpenAI-compatible inference servers (vLLM, SGLang, llama.cpp,
    or custom CodeMind serving daemon) exposing /v1/chat/completions.
    """

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:8000/v1",
        model_name: str = "codemind",
        timeout_seconds: int = 120,
        options: dict[str, Any] | None = None,
        context_window: int = 32768,
    ):
        super().__init__(
            endpoint=endpoint,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            options=options,
        )
        self.context_window = context_window
        self._capabilities = ModelCapabilityProfile(
            supports_streaming=True,
            supports_structured_output=True,
            supports_json_schema=True,
            supports_tool_calling=False,
            supports_system_messages=True,
            supports_cancellation=True,
            supports_usage_reporting=True,
            context_window=self.context_window,
            supports_multiple_tool_calls=False,
            is_mock=False,
            is_local=True,
        )

    @property
    def capability_profile(self) -> ModelCapabilityProfile:
        return self._capabilities

    async def check_health(self) -> HealthStatus:
        """Verify endpoint connectivity and model availability."""
        url = f"{self.endpoint}/models"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("id") or m.get("name") for m in data.get("data", [])]
                    target_found = self.model_name in models if models else True
                    return HealthStatus(
                        healthy=True,
                        details={
                            "endpoint": self.endpoint,
                            "models_available": models,
                            "target_model": self.model_name,
                            "target_found": target_found,
                            "status": "Ready",
                        },
                    )
                # Fallback to /health check
                health_url = self.endpoint.replace("/v1", "/health")
                resp_alt = await client.get(health_url)
                if resp_alt.status_code == 200:
                    data = resp_alt.json() if "application/json" in resp_alt.headers.get("content-type", "") else {}
                    service_name = str(data.get("service", "")).lower()
                    if "godot" in service_name or ("codemind" not in service_name and "model" not in service_name):
                        return HealthStatus(
                            healthy=False,
                            error=f"Endpoint {self.endpoint} is occupied by unrelated service: {data.get('service')}",
                            details={"endpoint": self.endpoint},
                        )
                    return HealthStatus(
                        healthy=True,
                        details={
                            "endpoint": self.endpoint,
                            "target_model": self.model_name,
                            "status": "Ready",
                        },
                    )
                return HealthStatus(
                    healthy=False,
                    error=f"Endpoint returned HTTP {resp.status_code} for /models and {resp_alt.status_code} for /health",
                    details={"endpoint": self.endpoint},
                )
        except httpx.ConnectError as err:
            return HealthStatus(
                healthy=False,
                error=f"Connection refused to {self.endpoint}: {err}",
                details={"endpoint": self.endpoint},
            )
        except Exception as ex:
            return HealthStatus(healthy=False, error=str(ex), details={"endpoint": self.endpoint})

    async def list_models(self) -> list[dict[str, Any]]:
        """Query /v1/models endpoint."""
        url = f"{self.endpoint}/models"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    model_list = []
                    for item in data.get("data", []):
                        mid = item.get("id") or item.get("name")
                        if mid:
                            model_list.append({
                                "name": mid,
                                "provider": "codemind-custom",
                                "details": item,
                            })
                    return model_list
        except Exception:
            pass
        return [{"name": self.model_name, "provider": "codemind-custom", "status": "Configured"}]

    def _estimate_tokens(self, messages: list[ChatMessage]) -> int:
        """Estimate token count across chat messages (~4 chars per token)."""
        total_chars = sum(len(m.content) for m in messages)
        return total_chars // 4

    async def generate(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        """Execute chat completion request with token budget validation and protocol normalization."""
        # 1. Context length check
        estimated_input_tokens = self._estimate_tokens(messages)
        if estimated_input_tokens > self.context_window:
            raise ContextOverflowError(
                f"Context length exceeded: ~{estimated_input_tokens} estimated tokens > {self.context_window} window limit."
            )

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
                        f"Custom model endpoint returned HTTP {resp.status_code}: {resp.text[:300]}"
                    )

                data = resp.json()
                choice = data["choices"][0]
                message_obj = choice.get("message", {})
                raw_content = message_obj.get("content") or ""
                if not raw_content and "reasoning" in message_obj:
                    raw_content = message_obj["reasoning"]

                finish_reason = choice.get("finish_reason", "stop")

                # Parse token usage
                usage = None
                if "usage" in data and data["usage"]:
                    u = data["usage"]
                    usage = ModelUsage(
                        prompt_tokens=u.get("prompt_tokens", estimated_input_tokens),
                        completion_tokens=u.get("completion_tokens", len(raw_content) // 4),
                        total_tokens=u.get("total_tokens", estimated_input_tokens + len(raw_content) // 4),
                    )

                # Defensive normalization to guaranteed CodeMind v1 protocol envelope
                normalized_content = ProtocolNormalizer.normalize_response_content(raw_content)

                return ModelResponse(
                    content=normalized_content,
                    usage=usage,
                    finish_reason=finish_reason,
                    raw_response=data,
                )

        except httpx.TimeoutException as ex:
            raise ModelTimeoutError(f"Custom model inference timed out after {self.timeout_seconds}s: {ex}")
        except httpx.ConnectError as ex:
            raise ModelUnavailableError(f"Failed to connect to CodeMind custom model endpoint at {self.endpoint}: {ex}")
        except Exception as ex:
            if isinstance(ex, (ModelError, ContextOverflowError)):
                raise
            raise ModelUnavailableError(f"Unexpected custom model error: {ex}")

    async def generate_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream SSE completion chunks."""
        estimated_input_tokens = self._estimate_tokens(messages)
        if estimated_input_tokens > self.context_window:
            raise ContextOverflowError(
                f"Context length exceeded: ~{estimated_input_tokens} estimated tokens > {self.context_window} window."
            )

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
                        raise ModelUnavailableError(f"Streaming failed with HTTP {resp.status_code}")
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
            raise ModelTimeoutError(f"Streaming timed out: {ex}")
        except httpx.ConnectError as ex:
            raise ModelUnavailableError(f"Connection refused at {self.endpoint}: {ex}")


class FallbackAwareModelAdapter(ModelAdapter):
    """Composite adapter that automatically switches to a fallback model if the primary is unavailable."""

    def __init__(
        self,
        primary_adapter: ModelAdapter,
        fallback_adapter: ModelAdapter,
        enable_fallback: bool = True,
    ):
        super().__init__(
            endpoint=primary_adapter.endpoint,
            model_name=primary_adapter.model_name,
            timeout_seconds=primary_adapter.timeout_seconds,
            options=primary_adapter.options,
        )
        self.primary = primary_adapter
        self.fallback = fallback_adapter
        self.enable_fallback = enable_fallback
        self.active_adapter_name: str = primary_adapter.model_name
        self.fallback_history: list[dict[str, Any]] = []

    @property
    def capability_profile(self) -> ModelCapabilityProfile:
        return self.primary.capability_profile

    async def check_health(self) -> HealthStatus:
        """Probe primary; if unhealthy and fallback enabled, probe fallback."""
        primary_health = await self.primary.check_health()
        if primary_health.healthy:
            return primary_health

        if self.enable_fallback:
            fallback_health = await self.fallback.check_health()
            if fallback_health.healthy:
                return HealthStatus(
                    healthy=True,
                    details={
                        "status": "Operating in Fallback Mode",
                        "primary_status": primary_health.error or "Unavailable",
                        "active_fallback": self.fallback.model_name,
                        "fallback_endpoint": self.fallback.endpoint,
                    },
                )
        return primary_health

    async def list_models(self) -> list[dict[str, Any]]:
        models = await self.primary.list_models()
        if self.enable_fallback:
            fb_models = await self.fallback.list_models()
            models.extend(fb_models)
        return models

    async def generate(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        """Attempt generation with primary; fall back cleanly if primary is unavailable."""
        try:
            resp = await self.primary.generate(messages, temperature=temperature, max_tokens=max_tokens)
            self.active_adapter_name = self.primary.model_name
            return resp
        except (ModelUnavailableError, ModelTimeoutError) as ex:
            if not self.enable_fallback:
                raise

            # Record fallback event
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "primary_model": self.primary.model_name,
                "fallback_model": self.fallback.model_name,
                "reason": str(ex),
            }
            self.fallback_history.append(event)
            logger.warning(
                f"Primary model '{self.primary.model_name}' unavailable ({ex}). "
                f"Routing to fallback model '{self.fallback.model_name}'."
            )

            resp = await self.fallback.generate(messages, temperature=temperature, max_tokens=max_tokens)
            self.active_adapter_name = self.fallback.model_name
            return resp

    async def generate_stream(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Attempt streaming with primary; fall back if primary is unavailable."""
        try:
            async for chunk in self.primary.generate_stream(messages, temperature=temperature, max_tokens=max_tokens):
                yield chunk
        except (ModelUnavailableError, ModelTimeoutError) as ex:
            if not self.enable_fallback:
                raise

            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "primary_model": self.primary.model_name,
                "fallback_model": self.fallback.model_name,
                "reason": str(ex),
            }
            self.fallback_history.append(event)
            logger.warning(f"Streaming primary failed ({ex}); routing to fallback '{self.fallback.model_name}'.")

            async for chunk in self.fallback.generate_stream(messages, temperature=temperature, max_tokens=max_tokens):
                yield chunk
