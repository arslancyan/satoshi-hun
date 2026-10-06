from challenge_adapter import ChallengeSourceAdapter

def test_base_adapter_never_infers_solve_from_balance_change():
    adapter = ChallengeSourceAdapter()
    assert adapter.is_authoritatively_solved({"balance_btc": 0}, {"spent": True}) is False

def test_base_funding_rule_requires_match_and_fresh_verification():
    adapter = ChallengeSourceAdapter()
    assert adapter.funding_is_valid({
        "status":"OPEN + FUNDED","balance_btc":1,
        "verification":{"funding_match":True,"verification_stale":False}
    })
    assert not adapter.funding_is_valid({
        "status":"OPEN + FUNDED","balance_btc":1,
        "verification":{"funding_match":False,"verification_stale":False}
    })
