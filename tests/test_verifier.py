import pytest

from verifier import ChallengeAdapter, register_adapter, verify_candidate_hash


def _record(challenge_type="hash-commitment", expected="abc123"):
    return {
        "id": "public-1",
        "type": challenge_type,
        "reward_btc": 0.01,
        "balance_btc": 0.01,
        "status": "OPEN + FUNDED",
        "rules": "public-reward-challenge",
        "provenance": {"url": "https://example.com/challenge", "source_id": "public-1"},
        "verification": {"method": "hash-commitment", "expected_candidate_hash": expected, "funding_match": True, "verification_stale": False},
    }


def test_unknown_public_challenge_cannot_verify():
    result = verify_candidate_hash(_record("unregistered-type"), "abc123")
    assert result["verified"] is False
    assert "No challenge-specific verifier" in result["reason"]


def test_hash_commitment_adapter_verifies_exact_hash():
    result = verify_candidate_hash(_record(), "abc123")
    assert result["verified"] is True


def test_hash_commitment_adapter_rejects_wrong_hash():
    result = verify_candidate_hash(_record(), "wrong")
    assert result["verified"] is False


def test_duplicate_adapter_registration_is_rejected():
    class DuplicateAdapter(ChallengeAdapter):
        challenge_type = "hash-commitment"

        def verify(self, record, candidate):
            return True

    with pytest.raises(ValueError, match="already registered"):
        register_adapter(DuplicateAdapter())


def test_adapter_requires_concrete_type():
    class EmptyAdapter(ChallengeAdapter):
        challenge_type = "unknown"

        def verify(self, record, candidate):
            return False

    with pytest.raises(ValueError, match="concrete"):
        register_adapter(EmptyAdapter())


def test_funded_status_is_required_for_verification():
    record = _record()
    record["status"] = "OPEN + UNFUNDED"
    result = verify_candidate_hash(record, "abc123")
    assert result["verified"] is False


def test_missing_provenance_is_not_solver_eligible():
    record = _record()
    record["provenance"] = {}
    result = verify_candidate_hash(record, "abc123")
    assert result["verified"] is False


def test_incomplete_provenance_metadata_is_not_solver_eligible():
    record = _record()
    record["provenance"] = {"url": "https://example.com/challenge", "source_id": "public-1"}
    result = verify_candidate_hash(record, "abc123")
    assert result["verified"] is False


def test_incomplete_verification_metadata_is_not_solver_eligible():
    record = _record()
    record["verification"] = {"method": "hash-commitment", "source_id": "public-1", "expected_candidate_hash": "abc123"}
    result = verify_candidate_hash(record, "abc123")
    assert result["verified"] is False


def test_non_object_metadata_is_not_solver_eligible():
    record = _record()
    record["provenance"] = "https://example.com/challenge"
    result = verify_candidate_hash(record, "abc123")
    assert result["verified"] is False


def test_peter_todd_hash_collision_adapter_contract():
    record=_record("hash-collision")
    record["provenance"]={"url":"https://github.com/floflo777/open-crypto-puzzles","source_id":"peter-todd-hash-collision-bounties","checked_at":"2026-08-16"}
    record["verification"]={"method":"published-hash-collision-rule","source_id":"peter-todd-hash-collision-bounties","checked_at":"2026-08-16","fingerprint":"public-puzzle-record"}
    result=verify_candidate_hash(record,"sha256:00:01")
    assert result["verified"] is False


def test_peter_todd_hash_collision_rejects_same_message():
    record=_record("hash-collision")
    record["provenance"]={"url":"https://github.com/floflo777/open-crypto-puzzles","source_id":"peter-todd-hash-collision-bounties","checked_at":"2026-08-16"}
    record["verification"]={"method":"published-hash-collision-rule","source_id":"peter-todd-hash-collision-bounties","checked_at":"2026-08-16","fingerprint":"public-puzzle-record"}
    assert verify_candidate_hash(record,"sha256:00:00")["verified"] is False


def _peter_todd_record():
    return {
        "id": "peter-todd-hash-collision-bounties",
        "type": "hash-collision",
        "reward_btc": 0.59364885,
        "balance_btc": 0.59364885,
        "status": "OPEN + FUNDED",
        "rules": "public-reward-challenge",
        "provenance": {
            "url": "https://bitcointalk.org/index.php?topic=293382.0",
            "source_id": "peter-todd-hash-collision-bounties-0-59btc",
            "checked_at": "2026-10-06",
        },
        "verification": {
            "method": "published P2SH hash-collision rule",
            "source_id": "peter-todd-hash-collision-bounties-0-59btc",
            "checked_at": "2026-10-06",
            "fingerprint": "four-live-escrows-public-record",
            "allowed_algorithms": ["sha256", "ripemd160", "hash160", "hash256"],
            "funding_match": True,
            "verification_stale": False,
        },
    }


def test_peter_todd_adapter_rejects_non_collision():
    assert verify_candidate_hash(_peter_todd_record(), "sha256:00:01")["verified"] is False


def test_peter_todd_adapter_rejects_same_message():
    assert verify_candidate_hash(_peter_todd_record(), "sha256:00:00")["verified"] is False


def test_peter_todd_adapter_rejects_unregistered_algorithm():
    assert verify_candidate_hash(_peter_todd_record(), "md5:00:01")["verified"] is False


def test_peter_todd_adapter_rejects_oversized_input():
    a = "00" * 521
    assert verify_candidate_hash(_peter_todd_record(), f"sha256:{a}:01")["verified"] is False


def test_peter_todd_adapter_binds_algorithm_to_registry():
    record = _peter_todd_record()
    record["verification"]["allowed_algorithms"] = ["ripemd160"]
    assert verify_candidate_hash(record, "sha256:00:01")["verified"] is False
