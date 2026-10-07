"""Promotion gate for public Satoshi Hunt challenge adapters.

A challenge may be promoted to RUNNABLE only when every safety/economic
requirement is explicitly satisfied. This module is intentionally pure so it
can be used by CI, ingestion, and operator tooling without touching funds.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChallengeQualification:
    provenance_verified: bool
    funding_verified: bool
    permissionless_payout: bool
    deterministic_verifier: bool
    bounded_search_space: bool
    test_vectors_present: bool
    audited_adapter: bool
    private_key_search: bool = False
    seed_phrase_search: bool = False
    generic_unbounded_bruteforce: bool = False

    @property
    def eligible(self) -> bool:
        return (
            self.provenance_verified
            and self.funding_verified
            and self.permissionless_payout
            and self.deterministic_verifier
            and self.bounded_search_space
            and self.test_vectors_present
            and self.audited_adapter
            and not self.private_key_search
            and not self.seed_phrase_search
            and not self.generic_unbounded_bruteforce
        )

    def reasons(self) -> list[str]:
        checks = (
            ("provenance_verified", self.provenance_verified),
            ("funding_verified", self.funding_verified),
            ("permissionless_payout", self.permissionless_payout),
            ("deterministic_verifier", self.deterministic_verifier),
            ("bounded_search_space", self.bounded_search_space),
            ("test_vectors_present", self.test_vectors_present),
            ("audited_adapter", self.audited_adapter),
        )
        reasons = [name for name, ok in checks if not ok]
        if self.private_key_search:
            reasons.append("private_key_search_forbidden")
        if self.seed_phrase_search:
            reasons.append("seed_phrase_search_forbidden")
        if self.generic_unbounded_bruteforce:
            reasons.append("generic_unbounded_bruteforce_forbidden")
        return reasons


def qualify_challenge(data: dict[str, Any]) -> dict[str, Any]:
    """Return an auditable, non-mutating promotion decision.

    Missing fields are false by design. A caller must prove every gate rather
    than relying on optimistic defaults.
    """
    q = ChallengeQualification(
        provenance_verified=bool(data.get("provenance_verified", False)),
        funding_verified=bool(data.get("funding_verified", False)),
        permissionless_payout=bool(data.get("permissionless_payout", False)),
        deterministic_verifier=bool(data.get("deterministic_verifier", False)),
        bounded_search_space=bool(data.get("bounded_search_space", False)),
        test_vectors_present=bool(data.get("test_vectors_present", False)),
        audited_adapter=bool(data.get("audited_adapter", False)),
        private_key_search=bool(data.get("private_key_search", False)),
        seed_phrase_search=bool(data.get("seed_phrase_search", False)),
        generic_unbounded_bruteforce=bool(data.get("generic_unbounded_bruteforce", False)),
    )
    return {
        "eligible": q.eligible,
        "reasons": q.reasons(),
        "required_gates": 7,
        "safety_forbidden": {
            "private_key_search": q.private_key_search,
            "seed_phrase_search": q.seed_phrase_search,
            "generic_unbounded_bruteforce": q.generic_unbounded_bruteforce,
        },
    }
