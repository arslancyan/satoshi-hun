import json
from pathlib import Path

from protocol import eligible as protocol_eligible
from registry import record_fingerprint
from verifier import eligible as verifier_eligible


ROOT = Path(__file__).resolve().parents[1]


def test_demo_registry_is_not_solver_eligible():
    data = json.loads((ROOT / "puzzles.json").read_text(encoding="utf-8"))
    assert data["verified"] is False
    assert all(not protocol_eligible(p) for p in data["puzzles"])


def test_registry_fingerprint_is_stable():
    record = {"b": 2, "a": 1}
    assert record_fingerprint(record) == record_fingerprint({"a": 1, "b": 2})


def test_verifier_requires_provenance_and_verification():
    base = {
        "status": "OPEN + FUNDED",
        "balance_btc": 1,
        "reward_btc": 1,
        "rules": "public-reward-challenge",
    }
    assert verifier_eligible(base) is False
    base["provenance"] = {"url": "https://example.com", "source_id": "test", "checked_at": "2026-01-01T00:00:00Z"}
    base["verification"] = {"method": "published-rule", "source_id": "test", "checked_at": "2026-01-01T00:00:00Z", "fingerprint": "abc", "funding_match": True, "verification_stale": False}
    assert verifier_eligible(base) is True


def test_protocol_requires_provenance_and_verification():
    record = {
        "status": "OPEN + FUNDED",
        "balance_btc": 1,
        "reward_btc": 1,
        "rules": "public-reward-challenge",
    }
    assert protocol_eligible(record) is False
    record["provenance"] = {"url": "https://example.com", "source_id": "test", "checked_at": "2026-01-01T00:00:00Z"}
    record["verification"] = {"method": "published-rule", "source_id": "test", "checked_at": "2026-01-01T00:00:00Z", "fingerprint": "abc", "funding_match": True, "verification_stale": False}
    assert protocol_eligible(record) is True

def test_verified_result_pipeline_requires_registered_adapter():
    from verifier import verify_candidate
    record = {
        "id": "adapter-test",
        "type": "unknown",
        "status": "OPEN + FUNDED",
        "balance_btc": 1,
        "reward_btc": 1,
        "rules": "public-reward-challenge",
        "provenance": {"url": "https://example.com/challenge", "source_id": "test", "checked_at": "2026-01-01T00:00:00Z"},
        "verification": {"method": "published-rule", "source_id": "test", "checked_at": "2026-01-01T00:00:00Z", "fingerprint": "abc", "funding_match": True, "verification_stale": False},
    }
    result = verify_candidate(record, "candidate")
    assert result["verified"] is False
    assert "No challenge-specific verifier" in result["reason"]

def test_hash_commitment_adapter_verifies_only_exact_hash():
    from verifier import verify_candidate_hash
    record = {
        "id": "hash-test",
        "type": "hash-commitment",
        "status": "OPEN + FUNDED",
        "balance_btc": 1,
        "reward_btc": 1,
        "rules": "public-reward-challenge",
        "provenance": {"url": "https://example.com/challenge", "source_id": "test", "checked_at": "2026-01-01T00:00:00Z"},
        "verification": {
            "method": "published hash commitment",
            "source_id": "test",
            "checked_at": "2026-01-01T00:00:00Z",
            "fingerprint": "abc",
            "expected_candidate_hash": "deadbeef",
            "funding_match": True,
            "verification_stale": False,
        },
    }
    assert verify_candidate_hash(record, "deadbeef")["verified"] is True
    assert verify_candidate_hash(record, "cafebabe")["verified"] is False
