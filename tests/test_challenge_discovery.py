from challenge_discovery import adapter_readiness, audit_discovered_challenges


def test_unknown_challenge_is_discovered():
    result = adapter_readiness("new-public-challenge")
    assert result["readiness"] == "DISCOVERED"
    assert result["execution_allowed"] is False


def test_research_challenge_stays_verified():
    result = adapter_readiness("keir-finlow-bates-blockchain-book-600ksats")
    assert result["readiness"] == "VERIFIED"
    assert result["execution_allowed"] is False


def test_runnable_challenge_is_explicitly_allowed():
    result = adapter_readiness("peter-todd-sha256-bounty")
    assert result["readiness"] == "RUNNABLE"
    assert result["execution_allowed"] is True


def test_batch_discovery_preserves_order():
    ids = ["new-public-challenge", "peter-todd-sha256-bounty"]
    assert [x["challenge_id"] for x in audit_discovered_challenges(ids)] == ids
