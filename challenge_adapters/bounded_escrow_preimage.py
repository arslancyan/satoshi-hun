"""Bounded SHA-256 preimage solver for permissionless P2WSH reward escrows.

The corresponding witness script is:
    OP_SHA256 <32-byte digest> OP_EQUALVERIFY OP_TRUE

Anyone who finds the bounded nonce can spend the escrow directly by providing
the preimage. Satoshi Hunt never holds a private key or signs the payout.
"""
from __future__ import annotations
import hashlib
from typing import Any

ADAPTER_ID = "bounded-escrow-preimage-v1"

def preimage(challenge_id: str, nonce: int) -> bytes:
    return f"{challenge_id}:{int(nonce)}".encode("utf-8")

def digest(challenge_id: str, nonce: int) -> str:
    return hashlib.sha256(preimage(challenge_id, nonce)).hexdigest()

def verify(challenge_id: str, difficulty_bits: int, nonce: int, submitted_hash: str, max_nonce: int) -> dict[str, Any]:
    if not challenge_id or not 1 <= int(difficulty_bits) <= 32:
        return {"valid": False, "reason": "invalid_challenge"}
    if int(nonce) < 0 or int(nonce) > int(max_nonce):
        return {"valid": False, "reason": "nonce_out_of_range"}
    actual = digest(challenge_id, int(nonce))
    value = int(actual, 16)
    target = 1 << (256 - int(difficulty_bits))
    ok = actual == str(submitted_hash).lower() and value < target
    return {
        "valid": ok,
        "reason": "ok" if ok else "proof_mismatch",
        "challenge_id": challenge_id,
        "difficulty_bits": int(difficulty_bits),
        "nonce": int(nonce),
        "hash": actual,
        "preimage": preimage(challenge_id, int(nonce)).decode("utf-8"),
    }

def solve(challenge_id: str, difficulty_bits: int, max_nonce: int, start_nonce: int = 0, max_attempts: int = 0) -> dict[str, Any] | None:
    start, end = max(0, int(start_nonce)), int(max_nonce)
    attempts = 0
    target = 1 << (256 - int(difficulty_bits))
    for nonce in range(start, end + 1):
        if max_attempts and attempts >= int(max_attempts):
            return None
        h = hashlib.sha256(preimage(challenge_id, nonce)).digest()
        attempts += 1
        if int.from_bytes(h, "big") < target:
            return {"nonce": nonce, "hash": h.hex(), "preimage": preimage(challenge_id, nonce).decode("utf-8"), "attempts": attempts}
    return None
