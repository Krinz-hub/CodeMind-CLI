"""Unit tests exposing defects in auth module."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import unittest
from auth import extract_user_role, is_token_valid


class TestAuth(unittest.TestCase):
    def test_valid_token_check(self) -> None:
        # Current time 1000 is before expiry 2000 -> Should be True
        self.assertTrue(is_token_valid(1000, 2000))

    def test_expired_token_check(self) -> None:
        # Current time 2500 is after expiry 2000 -> Should be False
        self.assertFalse(is_token_valid(2500, 2000))

    def test_role_extraction_with_missing_role(self) -> None:
        # Payload with no 'role' key should default to 'guest'
        payload = {"sub": "user_42", "email": "dev@codemind.local"}
        self.assertEqual(extract_user_role(payload), "guest")


if __name__ == "__main__":
    unittest.main()
