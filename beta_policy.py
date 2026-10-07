"""Closed-beta safety policy for Satoshi Hunt Phase 36.

Pure policy helpers keep beta access and challenge eligibility fail-closed.
No wallet custody, signing, or payout authority is granted by this module.
"""
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class BetaPolicy:
    enabled: bool
    max_active_workers: int = 10
    require_approved_worker: bool = True
    require_runnable_challenge: bool = True

    @property
    def valid(self) -> bool:
        return self.max_active_workers > 0


def beta_worker_eligible(*, policy: BetaPolicy, worker_status: str,
                         account_status: str, challenge_runnable: bool,
                         active_worker_count: int) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not policy.enabled:
        reasons.append("beta_disabled")
    if not policy.valid:
        reasons.append("invalid_beta_capacity")
    if policy.require_approved_worker and worker_status != "ACTIVE":
        reasons.append("worker_not_active")
    if account_status != "ACTIVE":
        reasons.append("account_not_active")
    if policy.require_runnable_challenge and not challenge_runnable:
        reasons.append("challenge_not_runnable")
    if active_worker_count >= policy.max_active_workers:
        reasons.append("beta_capacity_reached")
    return not reasons, reasons


def runnable_challenge_ids(challenges: Iterable[dict]) -> list[str]:
    result: list[str] = []
    for challenge in challenges:
        if challenge.get("runnable") is True and challenge.get("id"):
            result.append(str(challenge["id"]))
    return result
