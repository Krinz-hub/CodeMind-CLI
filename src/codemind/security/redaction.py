"""Redaction engine for scrubbing credentials and secrets from text and logs."""

from __future__ import annotations

import re

# Compiled patterns for secret detection
REDACTION_PATTERNS = [
    # Generic API Keys & Bearer tokens
    (re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-\.]{16,}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"(api[_-]?key\s*[:=]\s*['\"]?)[a-zA-Z0-9_\-]{16,}['\"]?", re.IGNORECASE), r"\1[REDACTED_API_KEY]"),
    (re.compile(r"(password\s*[:=]\s*['\"]?)[^\s'\"]{6,}['\"]?", re.IGNORECASE), r"\1[REDACTED_PASSWORD]"),
    (re.compile(r"(secret\s*[:=]\s*['\"]?)[^\s'\"]{8,}['\"]?", re.IGNORECASE), r"\1[REDACTED_SECRET]"),
    # OpenAI & typical sk- keys
    (re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE), "[REDACTED_OPENAI_KEY]"),
    # GitHub Tokens
    (re.compile(r"gh[pousr]_[a-zA-Z0-9]{36,}", re.IGNORECASE), "[REDACTED_GITHUB_TOKEN]"),
    # AWS Keys
    (re.compile(r"(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    # Private Key blocks
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        "[REDACTED_PRIVATE_KEY_BLOCK]",
    ),
]


def redact_secrets(text: str) -> str:
    """Mask known secret patterns with redacted placeholders."""
    if not text:
        return text

    scrubbed = text
    for pattern, replacement in REDACTION_PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)

    return scrubbed
