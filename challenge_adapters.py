"""Challenge-specific verifier/solver adapter registry.

The registry deliberately separates:
- DISCOVERED: public puzzle metadata is known.
- VERIFIED: derivation/oracle has reproducible test vectors.
- RUNNABLE: a bounded, challenge-specific compute solver exists and passes
  its vectors.

A puzzle never becomes COMPUTE merely because it has funding or a certified
derivation. This prevents a generic brute-force worker from being attached to
a puzzle whose search domain is undefined or requires human information.
"""

from dataclasses import dataclass

# Compatibility: this legacy registry file coexists with the challenge_adapters/
# adapter module directory. Expose the directory as a package search path so
# verifier imports remain valid without renaming the public registry module.
from pathlib import Path as _Path
__path__ = [str(_Path(__file__).with_name("challenge_adapters"))]
from typing import Callable, Any


@dataclass(frozen=True)
class AdapterSpec:
    challenge_id: str
    adapter_id: str
    execution_mode: str
    verifier_kind: str
    status: str
    target_format: str
    search_space: str | None = None
    solver_entrypoint: str | None = None
    test_vectors: tuple[dict[str, Any], ...] = ()
    notes: str = ""

    @property
    def runnable(self) -> bool:
        return (
            self.status in {"AUDITED", "RUNNABLE"}
            and self.execution_mode == "COMPUTE"
            and bool(self.solver_entrypoint)
            and bool(self.test_vectors)
        )


# Only adapters with a deterministic, independently testable compute path may
# enter RUNNABLE. Research puzzles can be VERIFIED without becoming runnable.
ADAPTERS: dict[str, AdapterSpec] = {
    "peter-todd-sha256-bounty": AdapterSpec(
        "peter-todd-sha256-bounty", "hash-collision-v1", "RESEARCH",
        "hash-collision", "VERIFIED", "unbounded full-width collision domain",
        None, None, (),
        "Public bounty is useful for research/verification analytics; no bounded audited compute adapter is approved.",
    ),
    "peter-todd-ripemd160-bounty": AdapterSpec(
        "peter-todd-ripemd160-bounty", "hash-collision-v1", "RESEARCH",
        "hash-collision", "VERIFIED", "unbounded full-width collision domain",
        None, None, (),
        "Public bounty is useful for research/verification analytics; no bounded audited compute adapter is approved.",
    ),
    "peter-todd-hash160-bounty": AdapterSpec(
        "peter-todd-hash160-bounty", "hash-collision-v1", "RESEARCH",
        "hash-collision", "VERIFIED", "unbounded full-width collision domain",
        None, None, (),
        "Public bounty is useful for research/verification analytics; no bounded audited compute adapter is approved.",
    ),
    "peter-todd-hash256-bounty": AdapterSpec(
        "peter-todd-hash256-bounty", "hash-collision-v1", "RESEARCH",
        "hash-collision", "VERIFIED", "unbounded full-width collision domain",
        None, None, (),
        "Public bounty is useful for research/verification analytics; no bounded audited compute adapter is approved.",
    ),
    # These are deliberately VERIFIED/RESEARCH: their published derivations
    # are reproducible, but solving requires external information or an
    # unbounded/unspecified corpus rather than a safe generic compute job.
    "corey-phillips-kitten-passphrase-1msats": AdapterSpec(
        "corey-phillips-kitten-passphrase-1msats", "bip39-passphrase-v1",
        "RESEARCH", "bip39-passphrase", "VERIFIED",
        "unknown author-chosen passphrase", None, None,
        ({"oracle": "published-sister-address", "empty_passphrase": True},),
        "Requires externally sourced passphrase evidence; no bounded public search domain.",
    ),
    "keir-finlow-bates-blockchain-book-600ksats": AdapterSpec(
        "keir-finlow-bates-blockchain-book-600ksats", "book-answer-v1",
        "RESEARCH", "book-answer", "VERIFIED",
        "human-derived answer strings", None, None,
        ({"oracle": "EN_easy_1", "answer": "221B Baker Street"},),
        "Open lots require information from physical book surfaces; not a generic compute search.",
    ),
    "rushwallet-contest-30-1msats": AdapterSpec(
        "rushwallet-contest-30-1msats", "brainwallet-v1",
        "RESEARCH", "brainwallet", "VERIFIED",
        "unknown passphrase corpus", None, None,
        ({"oracle": "public sibling brainwallets"},),
        "Derivation is certified but the missing passphrase source is not bounded.",
    ),
}


def get_adapter(challenge_id: str) -> AdapterSpec | None:
    return ADAPTERS.get(challenge_id)


def runtime_contract(challenge_id: str) -> dict[str, Any]:
    spec = get_adapter(challenge_id)
    if spec is None:
        return {
            "adapter_registered": False,
            "execution_mode": "RESEARCH",
            "runnable": False,
            "reason": "No challenge-specific adapter registered.",
        }
    return {
        "adapter_registered": True,
        "adapter_id": spec.adapter_id,
        "execution_mode": spec.execution_mode,
        "verifier_kind": spec.verifier_kind,
        "adapter_status": spec.status,
        "runnable": spec.runnable,
        "target_format": spec.target_format,
        "search_space": spec.search_space,
        "solver_entrypoint": spec.solver_entrypoint,
        "test_vectors": list(spec.test_vectors),
        "notes": spec.notes,
    }


def runnable_challenge_ids() -> set[str]:
    return {challenge_id for challenge_id, spec in ADAPTERS.items() if spec.runnable}


def validate_adapter(challenge_id: str, verifier: Callable[[dict[str, Any]], bool] | None = None) -> bool:
    """Validate registry metadata plus optional executable verifier.

    A future adapter promotion job can call this with the adapter's real
    verifier. Merely registering metadata can never promote a puzzle.
    """
    spec = get_adapter(challenge_id)
    if not spec or not spec.runnable:
        return False
    if verifier is None:
        return True
    return all(bool(verifier(vector)) for vector in spec.test_vectors)
