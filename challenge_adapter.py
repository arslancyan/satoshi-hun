"""Generic source-adapter contract.

Adapters may discover, refresh, and verify challenges. The base solve verifier is
deliberately conservative: no adapter may declare a challenge solved from a
balance change alone.
"""
from typing import Any

class ChallengeSourceAdapter:
    adapter_id = "abstract"

    def discover(self):
        raise NotImplementedError

    def refresh(self, record):
        raise NotImplementedError

    def is_authoritatively_solved(self, record, evidence):
        return False

    def evidence(self, record):
        return {"status": "UNKNOWN", "verified": False, "reason": "adapter_has_no_solve_rule"}

    def funding_is_valid(self, record):
        verification = record.get("verification") or {}
        return (
            record.get("status") == "OPEN + FUNDED"
            and float(record.get("balance_btc", 0)) > 0
            and verification.get("funding_match") is True
            and verification.get("verification_stale") is False
        )
