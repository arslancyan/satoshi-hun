"""Automatic public-challenge rotation engine."""
from dataclasses import dataclass
from typing import Any, Iterable

ELIGIBLE = {"OPEN + FUNDED"}

@dataclass(frozen=True)
class ChallengeDecision:
    active_id: str | None
    reason: str
    changed: bool
    retired_id: str | None = None

def authoritative_solved(record: dict[str, Any]) -> bool:
    evidence = record.get("external_status", {})
    return (evidence.get("status") == "SOLVED" and bool(evidence.get("verified"))
            and bool(evidence.get("evidence_url")) and bool(evidence.get("evidence_id")))

def eligible(record: dict[str, Any]) -> bool:
    if record.get("status") not in ELIGIBLE or float(record.get("balance_btc", 0) or 0) <= 0:
        return False
    return bool((record.get("provenance") or {}).get("url")) and bool((record.get("verification") or {}).get("method"))

def rank(record: dict[str, Any]) -> tuple[float, float, str]:
    return (float(record.get("balance_btc", 0) or 0), float(record.get("priority", 0) or 0), str(record.get("id", "")))

def choose_next(records: Iterable[dict[str, Any]], current_id: str | None) -> ChallengeDecision:
    rows = list(records)
    current = next((r for r in rows if r.get("id") == current_id), None)
    if current and authoritative_solved(current):
        current["status"] = "EXTERNAL_SOLVED"
        current["rotation"] = {"reason":"authoritative_external_solution",
                               "evidence_url":current["external_status"]["evidence_url"],
                               "evidence_id":current["external_status"]["evidence_id"]}
        candidates = [r for r in rows if r.get("id") != current_id and eligible(r)]
        candidates.sort(key=rank, reverse=True)
        if candidates:
            return ChallengeDecision(candidates[0]["id"], "rotated_after_external_solution", True, current_id)
        return ChallengeDecision(None, "no_eligible_funded_challenge", True, current_id)
    if current and eligible(current):
        return ChallengeDecision(current_id, "current_challenge_still_eligible", False)
    candidates = [r for r in rows if eligible(r)]
    candidates.sort(key=rank, reverse=True)
    if candidates:
        return ChallengeDecision(candidates[0]["id"], "selected_eligible_challenge", True, current_id)
    return ChallengeDecision(None, "no_eligible_funded_challenge", False, current_id)
