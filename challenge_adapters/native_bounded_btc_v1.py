"""Satoshi Hunt Native BTC Challenge v1.

This is a bounded nonce-search proof, not a wallet/private-key search.
The BTC reward is an escrow obligation verified separately on-chain.
"""
from __future__ import annotations
import hashlib
from typing import Any

ADAPTER_ID = "native-bounded-btc-v1"

def digest(challenge_id: str, nonce: int) -> str:
    return hashlib.sha256(f"{challenge_id}:{int(nonce)}".encode()).hexdigest()

def verify(challenge_id: str, difficulty_bits: int, nonce: int, submitted_hash: str, max_nonce: int) -> dict[str, Any]:
    if not challenge_id or not 1 <= int(difficulty_bits) <= 32:
        return {"valid": False, "reason": "invalid_challenge"}
    if int(nonce) < 0 or int(nonce) > int(max_nonce):
        return {"valid": False, "reason": "nonce_out_of_range"}
    actual = digest(challenge_id, int(nonce))
    ok = actual == str(submitted_hash).lower() and actual.startswith("0" * (int(difficulty_bits) // 4))
    if int(difficulty_bits) % 4:
        ok = actual == str(submitted_hash).lower() and bin(int(actual, 16))[2:].zfill(256).startswith("0" * int(difficulty_bits))
    return {"valid": ok, "reason": "ok" if ok else "proof_mismatch", "hash": actual, "nonce": int(nonce)}

def solve(challenge_id: str, difficulty_bits: int, max_nonce: int, start_nonce: int = 0, max_attempts: int = 0) -> dict[str, Any] | None:
    start, end = max(0, int(start_nonce)), int(max_nonce)
    attempts = 0
    for nonce in range(start, end + 1):
        if max_attempts and attempts >= int(max_attempts):
            return None
        h = digest(challenge_id, nonce)
        if bin(int(h, 16))[2:].zfill(256).startswith("0" * int(difficulty_bits)):
            return {"nonce": nonce, "hash": h, "attempts": attempts + 1}
        attempts += 1
    return None
