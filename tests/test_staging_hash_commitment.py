from datetime import datetime, timezone

from challenge_adapters.staging_hash_commitment import candidate_hash, verify


def test_staging_commitment_accepts_known_candidate():
    expected = candidate_hash("satoshi-hunt-staging-solution")
    result = verify(
        "satoshi-hunt-staging-solution",
        expected,
        expires_at="2099-01-01T00:00:00Z",
        now=datetime(2026, 10, 7, tzinfo=timezone.utc),
    )
    assert result["valid"] is True


def test_staging_commitment_rejects_expired_candidate():
    result = verify(
        "satoshi-hunt-staging-solution",
        candidate_hash("satoshi-hunt-staging-solution"),
        expires_at="2026-01-01T00:00:00Z",
        now=datetime(2026, 10, 7, tzinfo=timezone.utc),
    )
    assert result["valid"] is False
    assert result["reason"] == "expired"


def test_staging_commitment_rejects_replay():
    result = verify(
        "satoshi-hunt-staging-solution",
        candidate_hash("satoshi-hunt-staging-solution"),
        already_claimed=True,
    )
    assert result["valid"] is False
    assert result["reason"] == "already_claimed"


def test_registered_verifier_accepts_staging_hash_contract():
    from verifier import verify_candidate_hash

    record = {
        "id": "satoshi-hunt-staging-001",
        "type": "hash-commitment",
        "reward_btc": 0.001,
        "balance_btc": 0.001,
        "status": "OPEN + FUNDED",
        "rules": "public-reward-challenge",
        "provenance": {
            "url": "https://staging.satoshi-hunt.invalid/challenge/001",
            "source_id": "staging-001",
            "checked_at": "2026-01-01T00:00:00Z",
        },
        "verification": {
            "method": "exact_candidate_hash",
            "source_id": "staging-001",
            "checked_at": "2026-01-01T00:00:00Z",
            "fingerprint": "staging-known-solution-v1",
            "expected_candidate_hash": "b54609333c7f5082f8e8eb408e40a59d73e9fbe9f546c2adf75347cd941bd22d",
            "funding_match": True,
            "verification_stale": False,
            "adapter_id": "staging-hash-commitment-v1",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    }
    result = verify_candidate_hash(
        record,
        "b54609333c7f5082f8e8eb408e40a59d73e9fbe9f546c2adf75347cd941bd22d",
    )
    assert result["verified"] is True


def test_registered_verifier_rejects_expired_staging_contract():
    from verifier import verify_candidate_hash

    record = {
        "id": "satoshi-hunt-staging-001",
        "type": "hash-commitment",
        "reward_btc": 0.001,
        "balance_btc": 0.001,
        "status": "OPEN + FUNDED",
        "rules": "public-reward-challenge",
        "provenance": {"url": "x", "source_id": "staging-001", "checked_at": "2026-01-01T00:00:00Z"},
        "verification": {
            "method": "exact_candidate_hash",
            "source_id": "staging-001",
            "checked_at": "2026-01-01T00:00:00Z",
            "fingerprint": "staging-known-solution-v1",
            "expected_candidate_hash": "b54609333c7f5082f8e8eb408e40a59d73e9fbe9f546c2adf75347cd941bd22d",
            "funding_match": True,
            "verification_stale": False,
            "adapter_id": "staging-hash-commitment-v1",
            "expires_at": "2020-01-01T00:00:00Z",
        },
    }
    result = verify_candidate_hash(record, record["verification"]["expected_candidate_hash"])
    assert result["verified"] is False
    assert result["reason"] == "Candidate rejected by challenge adapter."
