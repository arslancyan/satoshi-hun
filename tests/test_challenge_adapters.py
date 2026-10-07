from challenge_adapters import get_adapter, runtime_contract, runnable_challenge_ids


def test_research_adapters_are_registered_but_not_runnable():
    for challenge_id in (
        "corey-phillips-kitten-passphrase-1msats",
        "keir-finlow-bates-blockchain-book-600ksats",
        "rushwallet-contest-30-1msats",
    ):
        spec = get_adapter(challenge_id)
        assert spec is not None
        assert spec.status == "VERIFIED"
        assert spec.execution_mode == "RESEARCH"
        assert not spec.runnable


def test_only_explicit_compute_adapters_are_runnable():
    ids = runnable_challenge_ids()
    assert ids == {
        "peter-todd-sha256-bounty",
        "peter-todd-ripemd160-bounty",
        "peter-todd-hash160-bounty",
        "peter-todd-hash256-bounty",
    }


def test_runtime_contract_exposes_research_reason():
    contract = runtime_contract("rushwallet-contest-30-1msats")
    assert contract["adapter_registered"] is True
    assert contract["runnable"] is False
    assert "bounded" in contract["notes"] or "passphrase" in contract["notes"]
