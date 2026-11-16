"""Local model service connectivity and lifecycle manager.

Provides safe discovery, status verification, and auto-start capabilities
for local inference providers (Ollama, CodeMind Custom, Mock).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
from typing import Any

import httpx

from codemind.cli.ui import TerminalUI
from codemind.config import ModelProvider, ModelSettings


def is_ollama_running(endpoint: str = "http://127.0.0.1:11434", timeout: float = 1.5) -> tuple[bool, list[str]]:
    """Check if Ollama server is running and return list of pulled model names."""
    url = f"{endpoint.rstrip('/')}/api/tags"
    try:
        res = httpx.get(url, timeout=timeout)
        if res.status_code == 200:
            data = res.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            return True, models
    except Exception:
        pass
    return False, []


def start_ollama_server(endpoint: str = "http://127.0.0.1:11434", timeout_seconds: float = 5.0) -> tuple[bool, str]:
    """Attempt to start local Ollama server if executable is available."""
    ollama_path = shutil.which("ollama")
    if not ollama_path:
        return False, "Ollama executable not found on PATH. Install it from https://ollama.com"

    running, _ = is_ollama_running(endpoint, timeout=0.5)
    if running:
        return True, "Ollama service is already active."

    try:
        subprocess.Popen(
            [ollama_path, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as ex:
        return False, f"Failed to spawn 'ollama serve': {ex}"

    # Poll until ready or timeout
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        running, _ = is_ollama_running(endpoint, timeout=0.8)
        if running:
            return True, f"Started local Ollama service at {endpoint}"
        time.sleep(0.5)

    return False, f"Started 'ollama serve' but endpoint did not become ready within {timeout_seconds}s"


async def check_provider_availability(model_cfg: ModelSettings) -> tuple[bool, str, dict[str, Any]]:
    """Check connectivity and model availability for the configured provider."""
    provider = model_cfg.provider

    if provider == ModelProvider.MOCK:
        return True, "Mock provider active (offline deterministic testing).", {"provider": "mock"}

    if provider == ModelProvider.OLLAMA:
        running, models = is_ollama_running(model_cfg.endpoint, timeout=2.0)
        if not running:
            return False, f"Ollama service unreachable at {model_cfg.endpoint}.", {"provider": "ollama", "running": False}

        # Check model presence
        target = model_cfg.model_name
        has_model = any(target == m or m.startswith(f"{target}:") or target.startswith(f"{m}:") for m in models)
        details = {"provider": "ollama", "running": True, "models": models, "has_model": has_model}
        if has_model:
            return True, f"Connected to Ollama at {model_cfg.endpoint} with model '{target}' ready.", details
        else:
            return True, f"Ollama is running, but model '{target}' is not in local library. Available: {', '.join(models) or 'none'}", details

    if provider == ModelProvider.CODEMIND_CUSTOM:
        # Check custom endpoint
        from codemind.models.custom import CodeMindCustomAdapter
        adapter = CodeMindCustomAdapter(model_cfg)
        health = await adapter.check_health()
        if health.healthy:
            return True, f"Connected to CodeMind Custom model at {model_cfg.endpoint}.", {"provider": "codemind-custom", "healthy": True}

        # If unhealthy, check fallback
        if model_cfg.enable_fallback:
            fallback_running, fallback_models = is_ollama_running(model_cfg.fallback_endpoint, timeout=2.0)
            if fallback_running:
                return True, (
                    f"CodeMind Custom service offline ({health.error or 'unreachable'}); "
                    f"using fallback Ollama with '{model_cfg.fallback_model}'."
                ), {"provider": "codemind-custom", "fallback_active": True, "models": fallback_models}

        return False, f"Custom model unreachable at {model_cfg.endpoint}: {health.error or 'connection refused'}", {"provider": "codemind-custom", "healthy": False}

    return False, f"Unknown model provider: {provider}", {}


async def ensure_model_service(
    model_cfg: ModelSettings,
    ui: TerminalUI | None = None,
    auto_start: bool = True,
) -> tuple[bool, str]:
    """Ensure that the local model service is running, attempting auto-start if needed."""
    ok, message, details = await check_provider_availability(model_cfg)
    if ok:
        return True, message

    # Attempt auto-start if Ollama
    if auto_start and (
        model_cfg.provider == ModelProvider.OLLAMA
        or (model_cfg.provider == ModelProvider.CODEMIND_CUSTOM and model_cfg.enable_fallback)
    ):
        target_endpoint = model_cfg.endpoint if model_cfg.provider == ModelProvider.OLLAMA else model_cfg.fallback_endpoint
        if ui:
            ui.print_info(f"Local inference service not detected at {target_endpoint}. Attempting to start Ollama ('ollama serve')...")
        started, start_msg = start_ollama_server(target_endpoint)
        if started:
            ok_after, msg_after, _ = await check_provider_availability(model_cfg)
            if ok_after:
                return True, "Successfully started and connected to Ollama service."

    return False, message
