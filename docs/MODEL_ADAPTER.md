# Model Adapter Specification: CodeMind CLI

## 1. Design & Objectives

The model layer abstracts all communication between the agent runtime and local/remote LLMs. The runtime never references vendor-specific network payloads directly.

### Principles:
- **Local-First Default:** Targets local endpoints (`localhost:8000`, `localhost:11434`, etc.) with zero mandatory cloud accounts.
- **Normalized Response Interface:** Standardizes chat tokens, usage metrics, and completion outputs into immutable Pydantic objects.
- **Graceful Capability Degradation:** Inspects model capabilities (streaming, structured output, system prompts) and gracefully falls back to non-streaming or prompt-based JSON schemas.

---

## 2. ModelAdapter Interface

```python
class ModelAdapter(ABC):
    @property
    @abstractmethod
    def capability_profile(self) -> ModelCapabilityProfile: ...

    @abstractmethod
    async def check_health(self) -> HealthStatus: ...

    @abstractmethod
    async def generate(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ModelResponse: ...

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]: ...
```

---

## 3. Adapters

### 3.1 `CodeMindLocalAdapter`
- Communicates with OpenAI-compatible HTTP serving interfaces (`/v1/chat/completions` and `/v1/models`).
- Target endpoints: local servers such as vLLM, SGLang, Ollama `/v1`, text-generation-webui, or custom CodeMind servers.
- Supports streaming SSE chunks and token counting where exposed.

### 3.2 `OllamaAdapter`
- Communicates natively with Ollama's local daemon API (`/api/chat` and `/api/tags`).
- Automatically lists installed models (`qwen3.6`, `mixtral`, `qwen2.5`) and supports native temperature/context settings.

### 3.3 `MockModelAdapter`
- Offline deterministic testing adapter.
- Configurable with scripted responses or custom callable hooks for comprehensive unit/integration testing without running any GPU/CPU model process.
