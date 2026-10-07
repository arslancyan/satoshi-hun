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


def test_registered_compute_adapters_audit_cleanly():
    for challenge_id in (
        "peter-todd-sha256-bounty",
        "peter-todd-ripemd160-bounty",
        "peter-todd-hash160-bounty",
        "peter-todd-hash256-bounty",
    ):
        assert audit.classify(challenge_id) == "RUNNABLE"
        assert audit.audit_adapter(ADAPTERS[challenge_id]) == []


def test_malformed_runnable_adapter_is_rejected():
    broken = replace(
        ADAPTERS["peter-todd-sha256-bounty"],
        search_space=None,
    )
    assert audit.audit_adapter(broken)
