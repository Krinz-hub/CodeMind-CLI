"""Authentication and token verification functions with deliberate defects."""

from __future__ import annotations


def is_token_valid(current_timestamp: int, expiry_timestamp: int) -> bool:
    """Check if token has not expired.
    
    A token is valid if current_timestamp is strictly less than expiry_timestamp.
    """
    # DEFECT 1: Inverted comparison logic
    return current_timestamp > expiry_timestamp


def extract_user_role(payload: dict) -> str:
    """Extract user role from token payload, defaulting to 'guest' if absent."""
    # DEFECT 2: Direct key indexing causes KeyError when 'role' is absent
    return payload["role"]
