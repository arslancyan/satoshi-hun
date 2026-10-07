"""Runtime adapter discovery/readiness helpers.

These helpers classify discovered public challenges without granting execution
rights. A missing adapter is DISCOVERED; a registered non-runnable adapter is
VERIFIED/RESEARCH; only a fully audited adapter can be RUNNABLE.
"""

from __future__ import annotations

from typing import Any, Iterable

from challenge_adapters import runtime_contract


def adapter_readiness(challenge_id: str) -> dict[str, Any]:
    contract = runtime_contract(challenge_id)
    if not contract.get("adapter_registered"):
        status = "DISCOVERED"
        reason = "No challenge-specific adapter is registered."
    elif contract.get("runnable"):
        status = "RUNNABLE"
        reason = "Registered compute adapter is runnable."
    elif contract.get("adapter_status") == "VERIFIED":
        status = "VERIFIED"
        reason = contract.get("notes") or "Adapter verification exists, but compute execution is not enabled."
    else:
        status = str(contract.get("adapter_status") or "DISCOVERED")
        reason = contract.get("reason") or "Adapter requires review before execution."
    return {
        "challenge_id": challenge_id,
        "readiness": status,
        "execution_allowed": status == "RUNNABLE",
        "reason": reason,
        "adapter": contract,
    }


def audit_discovered_challenges(challenge_ids: Iterable[str]) -> list[dict[str, Any]]:
    return [adapter_readiness(str(challenge_id)) for challenge_id in challenge_ids]
