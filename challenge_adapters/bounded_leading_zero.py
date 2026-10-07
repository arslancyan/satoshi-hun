"""Bounded leading-zero proof-of-work adapter.

This adapter is safe for public, explicitly bounded proof-of-work challenges.
It never handles wallets, private keys, seed phrases, or blockchain signing.
The challenge record must supply a finite max_nonce and the server-side verifier
must independently verify the resulting proof before any reward is credited.
"""
from __future__ import annotations
import hashlib
from typing import Any

ADAPTER_ID = "bounded-leading-zero-v1"

def proof_digest(challenge: str, nonce: int) -> str:
    return hashlib.sha256(f"{challenge}:{int(nonce)}".encode("utf-8")).hexdigest()

def verify(challenge: str, difficulty_bits: int, nonce: int, submitted_hash: str, max_nonce: int) -> dict[str, Any]:
    if not challenge:
        return {"valid": False, "reason": "missing_challenge"}
    if not 1 <= int(difficulty_bits) <= 32:
        return {"valid": False, "reason": "invalid_difficulty"}
    if int(nonce) < 0 or int(nonce) > int(max_nonce):
        return {"valid": False, "reason": "nonce_out_of_range"}
    actual = proof_digest(challenge, int(nonce))
    prefix_bits = bin(int(actual, 16))[2:].zfill(256)
    valid = prefix_bits[:int(difficulty_bits)] == "0" * int(difficulty_bits) and actual == str(submitted_hash).lower()
    return {"valid": valid, "reason": "ok" if valid else "hash_or_target_mismatch", "challenge": challenge, "difficulty_bits": int(difficulty_bits), "nonce": int(nonce), "hash": actual}

def solve(challenge: str, difficulty_bits: int, max_nonce: int, start_nonce: int = 0, max_attempts: int = 0) -> dict[str, Any] | None:
    if not challenge or not 1 <= int(difficulty_bits) <= 32:
        raise ValueError("invalid challenge or difficulty")
    start = max(0, int(start_nonce))
    end = int(max_nonce)
    if end < start:
        return None
    attempts = 0
    for nonce in range(start, end + 1):
        if max_attempts and attempts >= int(max_attempts):
            return None
        digest = proof_digest(challenge, nonce)
        if bin(int(digest, 16))[2:].zfill(256).startswith("0" * int(difficulty_bits)):
            return {"nonce": nonce, "hash": digest, "attempts": attempts + 1}
        attempts += 1
    return None
