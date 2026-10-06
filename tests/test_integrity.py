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
    base["provenance"] = {"url": "https://example.com", "checked_at": "2026-01-01T00:00:00Z"}
    base["verification"] = {"method": "published-rule", "checked_at": "2026-01-01T00:00:00Z", "fingerprint": "abc"}
    assert verifier_eligible(base) is True
