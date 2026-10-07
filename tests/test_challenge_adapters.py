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


def test_unbounded_public_collision_adapters_are_not_runnable():
    runnable = runnable_challenge_ids()
    assert "base-leading-zero-canary" in runnable
    for challenge_id in (
        "peter-todd-sha256-bounty",
        "peter-todd-ripemd160-bounty",
        "peter-todd-hash160-bounty",
        "peter-todd-hash256-bounty",
    ):
        spec = get_adapter(challenge_id)
        assert spec.status == "VERIFIED"
        assert spec.execution_mode == "RESEARCH"
        assert not spec.runnable


def test_runtime_contract_exposes_research_reason():
    contract = runtime_contract("rushwallet-contest-30-1msats")
    assert contract["adapter_registered"] is True
    assert contract["runnable"] is False
    assert "bounded" in contract["notes"] or "passphrase" in contract["notes"]


def test_bounded_public_pow_adapter_contract():
    contract = runtime_contract("base-leading-zero-canary")
    assert contract["adapter_registered"] is True
    assert contract["runnable"] is True
    assert contract["execution_mode"] == "COMPUTE"
    assert contract["adapter_audited"] is True


def test_audited_adapter_is_not_runnable_until_explicitly_enabled():
    from dataclasses import replace
    base = get_adapter("peter-todd-sha256-bounty")
    audited = replace(
        base,
        status="AUDITED",
        execution_mode="COMPUTE",
        search_space="bounded:test-domain",
        solver_entrypoint="challenge_adapter_audit:_digest",
        test_vectors=({"algorithm": "sha256", "message": "satoshi-hunt:0"},),
    )
    assert audited.audited is True
    assert audited.runnable is False
