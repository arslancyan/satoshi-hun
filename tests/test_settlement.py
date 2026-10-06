from decimal import Decimal
from settlement import build_reward_event, community_pool_candidate, transition

def test_settlement_state_machine():
    assert transition("REVIEW", "APPROVED") == "APPROVED"
    assert transition("APPROVED", "SETTLED") == "SETTLED"

def test_settlement_rejects_reopen():
    try:
        transition("SETTLED", "REVIEW")
    except ValueError:
        pass
    else:
        raise AssertionError("settled reward must not reopen")

def test_owner_only_community_pool():
    event = build_reward_event("account", "puzzle", "1")
    assert community_pool_candidate(event, False) == Decimal("0.00000000")
    assert community_pool_candidate(event, True) == Decimal("0.15000000")
