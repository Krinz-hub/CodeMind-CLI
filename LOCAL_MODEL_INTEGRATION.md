# Local Model Integration Report

**CodeMind CLI — Local Intelligence Providers**  
**Date:** November 14, 2026  
**Status:** Operational & Validated  

---

## 1. Executive Summary

CodeMind CLI has been upgraded to support local-first inference using locally installed models on this system. The agent runtime operates independently of specific model weights, using dynamic discovery, standardized adapters, and a non-destructive capability test suite.

The primary operational local intelligence provider is **`qwen3.6:35b`** via the local **Ollama** daemon at `http://127.0.0.1:11434`.

---

## 2. Local Environment Inspection

### 2.1 Hardware & Compute Resources
- **Host GPU:** NVIDIA GB10 (Driver 580.173.02, CUDA 13.0)
- **System Memory:** 121 GiB unified memory (~107 GiB available)
- **Host Platform:** Linux x86_64 (Ubuntu)

### 2.2 Inference Endpoints Detected
| Service | Endpoint | Protocol | Status |
|---|---|---|---|
| **Ollama Native API** | `http://127.0.0.1:11434` | `/api/chat`, `/api/tags`, `/api/show` | **Active / Healthy** |
| **Ollama OpenAI API** | `http://127.0.0.1:11434/v1` | `/v1/models`, `/v1/chat/completions` | **Active / Healthy** |
| **Godot Agent Service** | `http://127.0.0.1:8000/v1` | Custom FastAPI endpoints | Active (Domain-specific) |
| **DGX Dashboard** | `http://127.0.0.1:11000` | Web UI | Active |

---

## 3. Installed Models Discovered

All models were detected dynamically via `ModelDiscovery` without hardcoding:

| Model Name | Parameters | Quantization | Disk Footprint | Discovered Via |
|---|---|---|---|---|
| **`qwen3.6:35b`** | 35.5B | Q4_K_M | 21.1 GB | Ollama & OpenAI-local |
| **`qwen3.6:35b-a3b`** | 35.5B | Q4_K_M | 21.1 GB | Ollama & OpenAI-local |
| **`qwen2.5:72b`** | 72.7B | Q4_K_M | 44.2 GB | Ollama & OpenAI-local |
| **`mixtral:latest`** | 46.7B | Q4_0 | 24.6 GB | Ollama & OpenAI-local |
| **`llama3.2-vision:90b`** | 88.6B | Q4_K_M | 50.9 GB | Ollama & OpenAI-local |
| **`qwen3.5:122b-a10b-q4_K_M`**| 125.1B | Q4_K_M | 75.8 GB | Ollama & OpenAI-local |

---

## 4. Capability Benchmark Results

The 7-dimension agent capability test suite was executed against local models using non-destructive live probes:

```bash
codemind models test <model>
```

### 4.1 Evaluation Summary

| Capability Dimension | `qwen3.6:35b` | `mixtral:latest` | `qwen2.5:72b` |
|---|---|---|---|
| **1. Instruction Following** | **Passed** (3.67s) | Failed (Markdown escape) | **Passed** (4.12s) |
| **2. Structured JSON Generation** | **Passed** (11.46s) | **Passed** (0.98s) | **Passed** (2.55s) |
| **3. Tool-Call Formatting (v1)**| **Passed** (6.87s) | **Passed** (3.50s) | **Passed** (13.31s) |
| **4. Multi-Step Reasoning** | **Passed** (4.90s) | **Passed** (2.42s) | **Passed** (3.80s) |
| **5. Context Handling** | **Passed** (2.64s) | **Passed** (1.86s) | **Passed** (2.10s) |
| **6. Code Generation** | **Passed** (12.75s) | **Passed** (3.24s) | **Passed** (5.40s) |
| **7. Error Interpretation** | **Passed** (3.87s) | **Passed** (8.62s) | **Passed** (3.90s) |
| **Overall Score** | **7 / 7 (100%)** | **6 / 7 (85%)** | **7 / 7 (100%)** |
| **Agent Compatibility** | **Full (Autonomous Ready)** | **Full (Autonomous Ready)** | **Full (Autonomous Ready)** |

---

## 5. Live Multi-Turn Workflow Validation

A live project exploration task was executed with `qwen3.6:35b`:

```bash
codemind "Explain the structure of this project" -w examples/sample_project
```

### Execution Trace:
1. **Turn 1 (Inspect Manifest):**
   - Model formulated Tool Request: `read_file(path="pyproject.toml")`.
   - Runtime verified workspace boundary, read 9 lines, returned observation.
2. **Turn 2 (Inspect Source):**
   - Model formulated Tool Request: `read_file(path="src/calculator.py")`.
   - Runtime returned functions (`add`, `subtract`, `multiply`, `divide`).
3. **Turn 3 (Inspect Tests):**
   - Model formulated Tool Request: `read_file(path="tests/test_calculator.py")`.
   - Runtime returned test case suite.
4. **Turn 4 (Final Synthesis):**
   - Model synthesized structured architectural explanation.
   - Emitted valid `final` envelope with summary list.
   - Runtime saved recoverable session checkpoint to `.codemind/sessions/`.

---

## 6. CLI Management Commands

Developers can inspect and switch models seamlessly:

```bash
# List all discovered local models
codemind models list

# Inspect active model and provider
codemind models current

# Verify endpoint connectivity
codemind models status

# Switch active model (persisted to .codemind/config.json)
codemind models use qwen3.6:35b
codemind models use mixtral:latest
codemind models use qwen2.5:72b

# Run live capability benchmark suite
codemind models test qwen3.6:35b
```

---

## 7. Known Limitations & Recommendations

1. **Reasoning Models & Thinking Tokens:**
   - Models like `qwen3.6:35b` perform internal chain-of-thought (`"thinking"`).
   - The token ceiling (`max_tokens` / `num_predict`) is configured to at least 4096 so reasoning completes before JSON envelopes are emitted.
2. **Recommended Default Model:**
   - **`qwen3.6:35b`** is the recommended default. It achieves a 100% pass rate on all 7 agent capability dimensions, exhibits excellent structured envelope compliance, and has low memory latency on the NVIDIA GB10 GPU.
3. **Future CodeMind Foundation Model:**
   - When the custom CodeMind foundation checkpoint is ready, developers can switch immediately without code modifications:
     ```bash
     codemind models use codemind --provider codemind-local --endpoint http://localhost:8000/v1
     ```
