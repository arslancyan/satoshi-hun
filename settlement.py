"""Non-custodial reward settlement state machine for Satoshi Hunt.

This module only records accounting decisions. It never signs, broadcasts, or
custodies Bitcoin and never reads wallet credentials.
"""
from decimal import Decimal
from economy import split_reward

VALID_TRANSITIONS = {
    "REVIEW": {"APPROVED", "VOID"},
    "APPROVED": {"SETTLED", "VOID"},
    "SETTLED": set(),
    "VOID": set(),
}

def transition(status: str, target: str) -> str:
    if target not in VALID_TRANSITIONS.get(status, set()):
        raise ValueError(f"invalid settlement transition: {status} -> {target}")
    return target

def build_reward_event(account_id, puzzle_id, gross_btc):
    split = split_reward(gross_btc)
    return {
        "account_id": str(account_id),
        "puzzle_id": str(puzzle_id),
        "gross_reward_btc": split["gross"],
        "worker_share_btc": split["worker_share"],
        "platform_fee_btc": split["platform_fee"],
        "settlement_status": "REVIEW",
    }

def community_pool_candidate(reward_event, owner_allocated_fee=False):
    """Only the owner's explicitly allocated platform fee may enter this pool."""
    if not owner_allocated_fee:
        return Decimal("0.00000000")
    return Decimal(str(reward_event["platform_fee_btc"]))
