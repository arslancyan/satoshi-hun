"""Verifier for public SHA-256 proof-of-work challenge contracts.

This module only validates a submitted proof. It does not generate nonces.
"""

from __future__ import annotations

import hashlib
from typing import Any


def digest(challenge: str, nonce: int) -> str:
    return hashlib.sha256(f"{challenge}{int(nonce)}".encode("utf-8")).hexdigest()


def verify(
    challenge: str,
    difficulty: int,
    nonce: int,
    submitted_hash: str,
    *,
    max_nonce: int | None = None,
) -> dict[str, Any]:
    if not challenge:
        return {"valid": False, "reason": "missing_challenge"}
    if difficulty < 1 or difficulty > 8:
        return {"valid": False, "reason": "invalid_difficulty"}
    if nonce < 0:
        return {"valid": False, "reason": "invalid_nonce"}
    if max_nonce is not None and nonce > max_nonce:
        return {"valid": False, "reason": "nonce_out_of_range"}

    actual = digest(challenge, nonce)
    valid = actual == str(submitted_hash).lower() and actual.startswith("0" * difficulty)
    return {
        "valid": valid,
        "challenge": challenge,
        "difficulty": difficulty,
        "nonce": nonce,
        "hash": actual,
        "reason": "ok" if valid else "hash_or_target_mismatch",
    }
