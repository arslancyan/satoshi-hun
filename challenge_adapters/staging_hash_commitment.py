"""Deterministic staging verifier for the Satoshi Hunt reward rail.

This adapter exists only to exercise the full lifecycle in CI/staging.
It validates a candidate against a published commitment and rejects expired
or replayed submissions at the adapter boundary. It does not touch wallets
or private keys.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def candidate_hash(candidate: str) -> str:
    return hashlib.sha256(candidate.encode("utf-8")).hexdigest()


def verify(
    candidate: str,
    expected_hash: str,
    *,
    expires_at: str | None = None,
    now: datetime | None = None,
    already_claimed: bool = False,
) -> dict[str, Any]:
    if already_claimed:
        return {"valid": False, "reason": "already_claimed"}

    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return {"valid": False, "reason": "invalid_expiry"}
        current = now or datetime.now(timezone.utc)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if current >= expiry:
            return {"valid": False, "reason": "expired"}

    actual = candidate_hash(candidate)
    valid = actual == str(expected_hash).lower()
    return {
        "valid": valid,
        "candidate_hash": actual,
        "reason": "ok" if valid else "commitment_mismatch",
    }
