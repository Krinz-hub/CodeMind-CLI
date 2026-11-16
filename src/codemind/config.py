"""Configuration management for CodeMind CLI using Pydantic v2."""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class PermissionMode(str, Enum):
    READ_ONLY = "read-only"
    SUPERVISED = "supervised"
    TRUSTED = "trusted"


class ModelProvider(str, Enum):
    CODEMIND_CUSTOM = "codemind-custom"
    CODEMIND_LOCAL = "codemind-local"
    OLLAMA = "ollama"
    OPENAI_LOCAL = "openai-local"
    MOCK = "mock"


class ModelSettings(BaseModel):
    provider: ModelProvider = Field(
        default=ModelProvider.OLLAMA,
        description="Active model provider adapter (codemind-custom, ollama, openai-local, codemind-local, mock)",
    )
    model_name: str = Field(
        default="qwen3.6:35b",
        description="Target model name identifier",
    )
    endpoint: str = Field(
        default="http://127.0.0.1:11434",
        description="HTTP endpoint for local model inference",
    )
    timeout_seconds: int = Field(
        default=120,
        description="Timeout for model generation requests in seconds",
    )
    temperature: float = Field(
        default=0.2,
        description="Sampling temperature",
    )
    max_tokens: int = Field(
        default=4096,
        description="Maximum tokens to generate per turn",
    )
    context_window: int = Field(
        default=32768,
        description="Context window size in tokens",
    )
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="Model-specific inference parameters (e.g. seed, num_predict, top_p)",
    )
    fallback_provider: ModelProvider | None = Field(
        default=ModelProvider.OLLAMA,
        description="Fallback model provider if primary is unreachable",
    )
    fallback_model: str | None = Field(
        default="qwen3.6:35b",
        description="Fallback model name",
    )
    fallback_endpoint: str | None = Field(
        default="http://127.0.0.1:11434",
        description="Fallback model endpoint URL",
    )
    enable_fallback: bool = Field(
        default=True,
        description="Whether to automatically route to fallback provider on primary failure",
    )


class RuntimeSettings(BaseModel):
    max_turns: int = Field(
        default=20,
        description="Maximum turns allowed in an execution loop",
    )
    max_tool_calls: int = Field(
        default=30,
        description="Maximum total tool calls permitted in a single task",
    )
    max_output_bytes: int = Field(
        default=65536,
        description="Maximum bytes captured from tool stdout/stderr (64KB)",
    )
    tool_timeout_seconds: int = Field(
        default=60,
        description="Timeout for tool execution in seconds",
    )
    auto_verify: bool = Field(
        default=True,
        description="Automatically run discovered project tests upon finalization",
    )


class SecuritySettings(BaseModel):
    permission_mode: PermissionMode = Field(
        default=PermissionMode.SUPERVISED,
        description="Active permission mode (read-only, supervised, trusted)",
    )
    allow_external_paths: bool = Field(
        default=False,
        description="Allow reading or writing files outside workspace root",
    )
    redact_secrets: bool = Field(
        default=True,
        description="Mask sensitive keys, tokens, and credentials in logs and outputs",
    )


class CodeMindConfig(BaseModel):
    workspace_root: str = Field(
        default_factory=lambda: os.getcwd(),
        description="Canonical path to workspace root",
    )
    plain_mode: bool = Field(
        default=False,
        description="Disable ANSI color codes and animations",
    )
    model: ModelSettings = Field(default_factory=ModelSettings)
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)

    def save(self, workspace_dir: str | Path | None = None) -> Path:
        """Persist current configuration to .codemind/config.json."""
        ws_root = Path(workspace_dir or self.workspace_root).resolve()
        cm_dir = ws_root / ".codemind"
        cm_dir.mkdir(parents=True, exist_ok=True)
        config_path = cm_dir / "config.json"

        # Export config data excluding workspace_root (which is dynamic to each run)
        data = self.model_dump(mode="json")
        data.pop("workspace_root", None)

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return config_path

    @classmethod
    def load(
        cls,
        workspace_dir: str | Path | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> CodeMindConfig:
        """Load configuration respecting defaults, config files, and environment overrides."""
        ws_root = Path(workspace_dir or os.getcwd()).resolve()
        config_data: dict[str, Any] = {"workspace_root": str(ws_root)}

        # Check for NO_COLOR or plain flag in env
        if os.getenv("NO_COLOR") or os.getenv("CODEMIND_PLAIN"):
            config_data["plain_mode"] = True

        # Environment variable overrides
        if os.getenv("CODEMIND_ENDPOINT"):
            config_data.setdefault("model", {})["endpoint"] = os.getenv("CODEMIND_ENDPOINT")
        if os.getenv("CODEMIND_MODEL"):
            config_data.setdefault("model", {})["model_name"] = os.getenv("CODEMIND_MODEL")
        if os.getenv("CODEMIND_PROVIDER"):
            provider_str = os.getenv("CODEMIND_PROVIDER", "").lower()
            if provider_str in [p.value for p in ModelProvider]:
                config_data.setdefault("model", {})["provider"] = provider_str
        if os.getenv("CODEMIND_MODE"):
            mode_str = os.getenv("CODEMIND_MODE", "").lower()
            if mode_str in [m.value for m in PermissionMode]:
                config_data.setdefault("security", {})["permission_mode"] = mode_str

        # Local config file: .codemind/config.json or .codemind/config.toml
        cm_dir = ws_root / ".codemind"
        json_cfg = cm_dir / "config.json"
        if json_cfg.is_file():
            try:
                with open(json_cfg, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                    cls._deep_update(config_data, file_data)
            except Exception:
                pass

        if overrides:
            cls._deep_update(config_data, overrides)

        return cls(**config_data)

    @staticmethod
    def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> None:
        for k, v in source.items():
            if isinstance(v, dict) and k in target and isinstance(target[k], dict):
                CodeMindConfig._deep_update(target[k], v)
            else:
                target[k] = v
