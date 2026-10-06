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
        "verification": {"method": "hash-commitment", "expected_candidate_hash": expected},
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
