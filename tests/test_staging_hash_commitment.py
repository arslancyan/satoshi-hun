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
