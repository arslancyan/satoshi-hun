from challenge_qualification import ChallengeQualification, qualify_challenge


def _complete():
    return {
        "provenance_verified": True,
        "funding_verified": True,
        "permissionless_payout": True,
        "deterministic_verifier": True,
        "bounded_search_space": True,
        "test_vectors_present": True,
        "audited_adapter": True,
    }


def test_complete_qualification_is_eligible():
    result = qualify_challenge(_complete())
    assert result["eligible"] is True
    assert result["reasons"] == []


def test_missing_gate_is_fail_closed():
    data = _complete()
    data.pop("funding_verified")
    result = qualify_challenge(data)
    assert result["eligible"] is False
    assert "funding_verified" in result["reasons"]


def test_private_key_search_can_never_be_eligible():
    data = _complete()
    data["private_key_search"] = True
    result = qualify_challenge(data)
    assert result["eligible"] is False
    assert "private_key_search_forbidden" in result["reasons"]


def test_seed_phrase_and_unbounded_bruteforce_are_forbidden():
    data = _complete()
    data["seed_phrase_search"] = True
    data["generic_unbounded_bruteforce"] = True
    result = qualify_challenge(data)
    assert result["eligible"] is False
    assert "seed_phrase_search_forbidden" in result["reasons"]
    assert "generic_unbounded_bruteforce_forbidden" in result["reasons"]


def test_dataclass_gate_matches_public_contract():
    q = ChallengeQualification(**_complete())
    assert q.eligible
    assert q.reasons() == []
