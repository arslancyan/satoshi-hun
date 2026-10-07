from dataclasses import replace

import challenge_adapter_audit as audit
from challenge_adapters import ADAPTERS


def test_unregistered_challenge_is_discovered():
    assert audit.classify("unknown-public-puzzle") == "DISCOVERED"


def test_research_adapters_are_verified_but_not_runnable():
    for challenge_id in (
        "corey-phillips-kitten-passphrase-1msats",
        "keir-finlow-bates-blockchain-book-600ksats",
        "rushwallet-contest-30-1msats",
    ):
        assert audit.classify(challenge_id) == "VERIFIED"
        assert not ADAPTERS[challenge_id].runnable


def test_public_collision_adapters_are_research_only():
    for challenge_id in (
        "peter-todd-sha256-bounty",
        "peter-todd-ripemd160-bounty",
        "peter-todd-hash160-bounty",
        "peter-todd-hash256-bounty",
    ):
        assert audit.classify(challenge_id) == "VERIFIED"
        assert audit.audit_adapter(ADAPTERS[challenge_id]) == []


def test_malformed_runnable_adapter_is_rejected():
    broken = replace(
        ADAPTERS["peter-todd-sha256-bounty"],
        status="RUNNABLE",
        execution_mode="COMPUTE",
        search_space=None,
        solver_entrypoint="backend.api:_managed_hash_digest",
        test_vectors=({"algorithm": "sha256", "message": "satoshi-hunt:0"},),
    )
    assert audit.audit_adapter(broken)


def test_audited_lifecycle_is_distinct_from_verified():
    from dataclasses import replace
    base = ADAPTERS["peter-todd-sha256-bounty"]
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
    assert audit.audit_adapter(audited) == []
