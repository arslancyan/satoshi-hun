"""Single policy for public challenge marketplace/worker queue eligibility.

This is a gate, not a solver. It only evaluates already-published registry
metadata, funding evidence, payout contract flags, and audited adapter state.
"""

from __future__ import annotations
from typing import Any


def queue_gate(record: dict[str, Any]) -> dict[str, Any]:
    verification = record.get("verification") or {}
    payout = record.get("payout") or {}
    reasons: list[str] = []

    if record.get("rules") != "public-reward-challenge":
        reasons.append("not_public_reward_challenge")
    if record.get("status") != "OPEN + FUNDED":
        reasons.append("not_open_funded")
    try:
        balance = float(record.get("balance_btc") or 0)
    except (TypeError, ValueError):
        balance = 0.0
    if balance <= 0:
        reasons.append("no_positive_balance")
    if verification.get("funding_match") is not True:
        reasons.append("funding_not_verified")
    stale = record.get("verification_stale")
    if stale is None:
        stale = verification.get("verification_stale")
    if stale is not False:
        reasons.append("verification_stale")
    if verification.get("execution_mode") != "COMPUTE":
        reasons.append("execution_mode_not_compute")
    if verification.get("adapter_audited") is not True:
        reasons.append("adapter_not_audited")
    if verification.get("adapter_runnable") is not True:
        reasons.append("adapter_not_runnable")
    if str(verification.get("adapter_status") or "").upper() != "RUNNABLE":
        reasons.append("adapter_status_not_runnable")
    if payout.get("permissionless") is not True:
        reasons.append("payout_not_permissionless")
    if payout.get("automatic_chain_claim") is not True:
        reasons.append("automatic_chain_claim_disabled")

    return {
        "eligible": not reasons,
        "reasons": reasons,
        "balance_btc": balance,
        "adapter_id": verification.get("adapter_id"),
    }


def is_queue_eligible(record: dict[str, Any]) -> bool:
    return bool(queue_gate(record)["eligible"])
