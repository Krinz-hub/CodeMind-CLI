"""Unit tests for secret and token redaction."""

import unittest

from codemind.security.redaction import redact_secrets


class TestRedaction(unittest.TestCase):
    def test_redact_openai_key(self) -> None:
        raw = "API key was sk-1234567890abcdef1234567890abcdef."
        cleaned = redact_secrets(raw)
        self.assertNotIn("sk-1234567890", cleaned)
        self.assertIn("[REDACTED_OPENAI_KEY]", cleaned)

    def test_redact_github_token(self) -> None:
        raw = "Token is ghp_1234567890abcdef1234567890abcdef1234"
        cleaned = redact_secrets(raw)
        self.assertNotIn("ghp_", cleaned)
        self.assertIn("[REDACTED_GITHUB_TOKEN]", cleaned)

    def test_redact_bearer_header(self) -> None:
        raw = "Authorization: Bearer my_super_secret_jwt_token_1234567"
        cleaned = redact_secrets(raw)
        self.assertIn("[REDACTED_TOKEN]", cleaned)

    def test_leave_clean_text_intact(self) -> None:
        raw = "def calculate_sum(a: int, b: int) -> int: return a + b"
        cleaned = redact_secrets(raw)
        self.assertEqual(raw, cleaned)
