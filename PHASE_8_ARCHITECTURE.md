# CodeMind Phase 8 — Custom Model Integration & Runtime Compatibility
## Architecture Specification

**Author:** Principal AI Systems Architect & Senior Software Engineer  
**Date:** November 16, 2026  
**Status:** Approved for Implementation  
**Target:** Model-Independent Foundation with Native CodeMind Custom Model Integration

---

## 1. Architectural Objectives

Phase 8 elevates CodeMind into a fully **model-independent software engineering system** capable of hosting our proprietary foundation model (**CodeMind-15M**) as its primary intelligence provider, while seamlessly supporting local community models (`qwen3.6:35b`) through Ollama and deterministic test adapters (`MockModelAdapter`).

### Non-Negotiable Constraints:
1. **Preserve Agent Runtime**: Do not alter the core execution loop, planning DAG, tool registry, or multi-agent coordinator topology.
2. **Zero Weight Alterations**: Do not download, train, or modify any model weights.
3. **Normalized Provider Contract**: All model interactions must flow through the normalized `ModelAdapter` interface without model-specific conditionals polluting the agent runtime.
4. **Observable Fallback Routing**: If the custom model endpoint is unreachable, CodeMind must record the event and gracefully route requests to a verified fallback provider (Ollama `qwen3.6:35b`), never reporting that the custom model is active unless it has initialized successfully.

---

## 2. Dedicated Provider Architecture

```
                       ┌──────────────────────────────┐
                       │   MultiAgentCoordinator /    │
                       │     Agent Execution Loop     │
                       └──────────────┬───────────────┘
                                      │
                                      ▼
                       ┌──────────────────────────────┐
                       │     ModelAdapter (Base)      │
                       │ - capability_profile         │
                       │ - check_health()             │
                       │ - list_models()              │
                       │ - generate()                 │
                       │ - generate_stream()          │
                       └──────────────┬───────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         │                            │                            │
         ▼                            ▼                            ▼
┌──────────────────┐        ┌───────────────────┐        ┌──────────────────┐
│  OllamaAdapter   │        │CodeMindCustom     │        │ MockModelAdapter │
│  (Ollama HTTP API│        │Adapter            │        │ (Hermetic Offline│
│  /api/chat)      │        │(OpenAI-Compatible │        │ Testing Suite)   │
│                  │        │/v1 REST Endpoint) │        │                  │
└──────────────────┘        └─────────┬─────────┘        └──────────────────┘
                                      │
                                      │ Unreachable / Offline
                                      ▼
                            ┌───────────────────┐
                            │ Fallback Engine   │
                            │ (Transparently    │
                            │ routes to Ollama/ │
                            │ qwen3.6:35b with  │
                            │ audit logging)    │
                            └───────────────────┘
```

### Component Breakdown:
- **`ModelAdapter` (`src/codemind/models/base.py`)**: Abstract base contract.
- **`CodeMindCustomAdapter` (`src/codemind/models/custom.py`)**: Dedicated adapter for the custom CodeMind model. Implements health checks, context overflow detection, token budgeting, prompt normalization, streaming, and defensive protocol extraction.
- **`FallbackAwareModelAdapter` (`src/codemind/models/custom.py`)**: Composite wrapper that initializes the primary custom adapter and automatically falls back to an alternate adapter if the primary is unhealthy or throws connection errors.
- **`OllamaAdapter` (`src/codemind/models/ollama.py`)**: Native client for Ollama local daemon.
- **`MockModelAdapter` (`src/codemind/models/mock.py`)**: In-memory deterministic adapter for 100% offline regression testing.

---

## 3. Configuration & Provider Selection Schema

The configuration system (`src/codemind/config.py`) is enhanced with first-class provider selection and fallback parameters:

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
    timeout_seconds: int = Field(default=120)
    temperature: float = Field(default=0.2)
    max_tokens: int = Field(default=4096)
    context_window: int = Field(default=32768)
    options: dict[str, Any] = Field(default_factory=dict)

    # Phase 8 Fallback Architecture
    fallback_provider: ModelProvider | None = Field(default=ModelProvider.OLLAMA)
    fallback_model: str | None = Field(default="qwen3.6:35b")
    fallback_endpoint: str | None = Field(default="http://127.0.0.1:11434")
    enable_fallback: bool = Field(default=True)
```

---

## 4. Protocol Compatibility & Defensive Normalization

CodeMind v1 protocol enforces versioned JSON response envelopes:
- `tool_call`: `{"protocol_version": "1", "type": "tool_call", "tool": "<name>", "arguments": {...}, "reason": "..."}`
- `plan`: `{"protocol_version": "1", "type": "plan", "tasks": [...], "reason": "..."}`
- `final`: `{"protocol_version": "1", "type": "final", "content": "...", "summary": [...]}`

The custom adapter integrates a **Safe Protocol Normalization Layer** (`ProtocolNormalizer`) to handle the 10 failure categories:

| Failure Category | Detection Mechanism | Normalization / Safe Handling |
|---|---|---|
| **1. Valid Tool Call** | Clean JSON matching schema | Emitted directly to runtime permission checker. |
| **2. Multiple Tool Calls** | JSON array or multiple objects | Serialized into first valid action; subsequent actions queued or rejected. |
| **3. Missing Arguments** | Missing required keys in `arguments` | Converted to `MalformedAction` requesting explicit parameter clarification. |
| **4. Invalid JSON** | `json.loads` failure | Regex searches for `{...}` blocks or markdown code fences; if unrecoverable, returns `MalformedAction`. |
| **5. Incorrect Protocol Version** | Missing or non-`"1"` version | Injected with `"protocol_version": "1"` if schema otherwise valid. |
| **6. Unexpected Formats** | Raw unstructured conversational text | Wrapped into `FinalAction` content rather than hallucinating a tool call. |
| **7. Truncated Responses** | Incomplete brackets / trailing ellipsis | Flagged as `MalformedAction(error_code="TRUNCATED")` triggering continuation. |
| **8. Empty Responses** | Whitespace-only content | Returned as `MalformedAction(error_code="EMPTY_RESPONSE")`. |
| **9. Context Overflow** | Prompt length > `context_window` | Pre-inference check raises `ContextOverflowError` before socket transmission. |
| **10. Untrusted Instructions** | Prompt injection / forbidden escapes | Sandboxed and validated through existing `WorkspaceSandbox` and `PermissionChecker`. |

---

## 5. Multi-Agent Compatibility Across All 4 Worker Roles

The multi-agent system from Phase 7 preserves strict compatibility with the custom adapter:
1. **ResearchWorker (`READ_ONLY`)**: Receives prompt with codebase reconnaissance instructions; model output parsed into `MessageType.FINDINGS`.
2. **CodingWorker (`TRUSTED` Sandbox)**: Produces multi-file implementations in isolated sandbox; outputs parsed into `MessageType.CHANGE_PROPOSAL`.
3. **DebuggingWorker (`TRUSTED` Sandbox)**: Receives stack trace; output parsed into repair diffs.
4. **TestingWorker (`TRUSTED` Sandbox)**: Authors AAA test suites; executes test suite in sandbox.
5. **InferenceGate Preservation**: All worker turns pass through the `InferenceGate` semaphore (`max_concurrent=1`), guaranteeing zero GPU memory contention regardless of the active provider.

---

## 6. Phase 8 Benchmark Suite Specification (`benchmarks/phase_8/`)

The evaluation harness evaluates 15 comprehensive categories (A through O):
- **Category A**: Protocol compliance (Envelope parsing and schema validation).
- **Category B**: Project understanding (Discovery of architecture and dependencies).
- **Category C**: Repository exploration (Targeted file discovery without exhaustive reads).
- **Category D**: Tool selection (Appropriate tool selection for task intent).
- **Category E**: Tool argument correctness (Valid paths, valid schemas, valid unified diffs).
- **Category F**: Single-file code generation (Synthesizing isolated modules).
- **Category G**: Multi-file code generation (Interdependent module implementation).
- **Category H**: Feature implementation (Full feature delivery against requirements).
- **Category I**: Bug diagnosis (Root-cause isolation from test traces).
- **Category J**: Bug repair (Minimal surgical patching).
- **Category K**: Test generation (AAA pattern test suite creation).
- **Category L**: Test failure recovery (Iterative repair when tests fail).
- **Category M**: Long-context handling (Token-heavy prompts up to 32k window).
- **Category N**: Multi-agent coordination (Worker delegation and role handoffs).
- **Category O**: End-to-end feature delivery (Decomposition, implementation, verification).

All scenarios compare:
1. `qwen3.6:35b` (Baseline)
2. `CodeMindCustomAdapter` (Custom model with fallback)
3. `MockModelAdapter` (Deterministic offline baseline)
