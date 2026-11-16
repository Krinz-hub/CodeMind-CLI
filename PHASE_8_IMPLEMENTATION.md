# CodeMind Phase 8 — Custom Model Integration & Runtime Compatibility
## Implementation Report

**Author:** Principal AI Systems Architect & Senior Software Engineer  
**Date:** November 16, 2026  
**Status:** Complete & Fully Verified  
**Runtime Baseline:** Model-Independent, Local-First, Zero Weight Alterations  

---

## 1. Executive Summary

Phase 8 elevates the CodeMind CLI agent platform into a **model-independent software engineering system**. CodeMind is now architected to host our proprietary foundation model (**CodeMind-15M**) as its primary intelligence provider, with community foundation models (`qwen3.6:35b` via local Ollama) operating as the production baseline and transparent fallback provider, and `MockModelAdapter` providing hermetic offline deterministic verification.

All capabilities were implemented strictly within the sanctions of the agent runtime:
- **Zero Model Weight Modification:** No weights downloaded, altered, trained, or fine-tuned.
- **Zero Tokenizer or Dataset Changes:** Tokenizer and training pipelines in `/home/piet/Documents/Codemind` remain completely untouched.
- **Runtime Preservation:** All Phase 7 multi-agent collaboration architecture—including `MultiAgentCoordinator`, all 4 specialized worker roles (`ResearchWorker`, `CodingWorker`, `DebuggingWorker`, `TestingWorker`), `SidecarRuntime`, `InferenceGate`, `WorkerWorkspaceManager`, and `MessageRouter`—was preserved with 100% regression compatibility.
- **Test Integrity:** Expanded the hermetic offline test suite from 91 to **103 passing tests** (100% pass rate in 1.79s).

---

## 2. Component Implementation Details

### 2.1 Custom Model Adapter (`src/codemind/models/custom.py`)

Implements `CodeMindCustomAdapter` subclassing `ModelAdapter` to connect to OpenAI-compatible `/v1` REST endpoints (serving CodeMind-15M):

```python
class CodeMindCustomAdapter(ModelAdapter):
    """Adapter for custom proprietary CodeMind foundation models."""
```

Key features:
1. **Preflight Context Overflow Detection:** Calculates prompt token size using character heuristics (`_estimate_tokens`); raises `ContextOverflowError` before transmission if payload exceeds `context_window` (defaults to 32,768 tokens, expandable to 65,536).
2. **Defensive Response Normalization:** Routes all completions through `ProtocolNormalizer` before emitting to the agent execution loop or permission checker.
3. **SSE Streaming Support:** Implements `generate_stream()` over Server-Sent Events (`/v1/chat/completions`) for real-time terminal output.
4. **Service Health Discrimination:** Discriminates between genuine CodeMind model services and foreign local daemons (such as the Godot AI Agent service on port 8000), preventing false claims of custom model activity.

### 2.2 Transparent Fallback Architecture (`FallbackAwareModelAdapter`)

Implements `FallbackAwareModelAdapter` as a composite decorator wrapping primary and fallback adapters:

```python
class FallbackAwareModelAdapter(ModelAdapter):
    """Composite adapter routing requests to fallback when primary is unavailable."""
```

1. **Observable Fallback Routing:** If the custom model endpoint is unreachable (e.g. HTTP 404, connection refused, or timeout), calls are transparently dispatched to the configured fallback adapter (`qwen3.6:35b` via Ollama).
2. **Audit Telemetry:** Every fallback occurrence is recorded in `self.fallback_history` with UTC timestamp, primary model name, fallback model name, and exact error diagnostics.
3. **Honest Status Reporting:** `check_health()` returns `"Operating in Fallback Mode"` with diagnostic details rather than falsely reporting primary readiness when offline.

### 2.3 Defensive Protocol Normalizer (`ProtocolNormalizer`)

Defensively sanitizes raw model completions into compliant CodeMind v1 JSON protocol envelopes (`tool_call`, `plan`, `final`, `malformed`):

```python
class ProtocolNormalizer:
    @classmethod
    def normalize_response_content(cls, raw_content: str) -> str:
        # 1. Strip reasoning/thinking tokens (<think>...</think>)
        # 2. Extract JSON from markdown fences (```json ... ```)
        # 3. Direct JSON parsing and outermost brace discovery
        # 4. Safe envelope validation (injecting protocol_version: "1")
        # 5. Non-JSON conversational text safely wrapped into FinalAction
```

### 2.4 Configuration Schema Enhancements (`src/codemind/config.py`)

Extended `ModelSettings` with first-class provider selection and fallback configuration:

```python
class ModelProvider(str, Enum):
    CODEMIND_CUSTOM = "codemind-custom"
    CODEMIND_LOCAL = "codemind-local"
    OLLAMA = "ollama"
    OPENAI_LOCAL = "openai-local"
    MOCK = "mock"

class ModelSettings(BaseModel):
    provider: ModelProvider = Field(default=ModelProvider.OLLAMA)
    model_name: str = Field(default="qwen3.6:35b")
    endpoint: str = Field(default="http://127.0.0.1:11434")
    fallback_provider: ModelProvider | None = Field(default=ModelProvider.OLLAMA)
    fallback_model: str | None = Field(default="qwen3.6:35b")
    fallback_endpoint: str | None = Field(default="http://127.0.0.1:11434")
    enable_fallback: bool = Field(default=True)
```

### 2.5 Dynamic Provider Discovery (`src/codemind/models/discovery.py`)

Updated `ModelDiscovery` to probe both community Ollama daemons (`127.0.0.1:11434`) and custom model endpoints (`127.0.0.1:8000/v1`), accurately registering `codemind-custom` in available model catalogs.

### 2.6 Extended CLI Capabilities (`src/codemind/cli/models_cli.py`)

Enhanced the `codemind models` command suite:
- `codemind models current`: Displays active provider, endpoint, fallback status, and active adapter name.
- `codemind models status`: Probes endpoint health and displays whether the system is operating in standard or fallback mode.
- `codemind models compare`: Added new subcommand comparing capability profiles, context limits, and roles across `qwen3.6:35b`, `codemind-custom`, and `mock`.
- `codemind models use <provider>`: Configures active provider with validation.

---

## 3. Verification & Regression Analysis

### 3.1 Unit Test Suite (`tests/unit/test_custom_model.py`)
10 tests verifying:
- Capability profiles and tool calling support
- Context window overflow exception before network I/O
- Valid tool call parsing and schema preservation
- Markdown fenced JSON block extraction
- Removal of `<think>` reasoning tags
- Safe conversion of conversational text to `FinalAction`
- Empty response detection
- Fallback invocation when primary endpoint is unreachable
- Factory composite instantiation

### 3.2 Integration Test Suite (`tests/integration/test_provider_switching.py`)
2 comprehensive integration tests verifying:
- CLI provider switching (`codemind models use` and `codemind models compare`)
- Multi-agent workflow execution through `FallbackAwareModelAdapter` under simulated primary downtime

### 3.3 Test Suite Execution Results
```
Ran 103 tests in 1.791s
OK (All 103 tests passed successfully)
```

No existing capabilities from Phases 1–7 were degraded or broken.
