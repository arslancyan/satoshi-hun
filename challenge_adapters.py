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
    def audited(self) -> bool:
        return self.status in {"AUDITED", "RUNNABLE"}

    @property
    def runnable(self) -> bool:
        return (
            self.status == "RUNNABLE"
            and self.execution_mode == "COMPUTE"
            and bool(self.solver_entrypoint)
            and bool(self.test_vectors)
        )


# Only adapters with a deterministic, independently testable compute path may
# enter RUNNABLE. Research puzzles can be VERIFIED without becoming runnable.
ADAPTERS: dict[str, AdapterSpec] = {
    "satoshi-hunt-native-btc-v1": AdapterSpec(
        "satoshi-hunt-native-btc-v1", "native-bounded-btc-v1", "COMPUTE",
        "sha256-leading-zero-proof", "RUNNABLE", "0..1048575 nonce range",
        "0..1048575", "challenge_adapters.native_bounded_btc_v1:solve",
        (
            {"challenge_id": "satoshi-hunt-native-btc-v1", "difficulty_bits": 16, "max_nonce": 1048575},
        ),
        "Satoshi Hunt-authored bounded nonce proof. It is not a private-key or seed search. Production promotion still requires a dedicated funded BTC escrow.",
    ),
    "satoshi-hunt-native-btc-quick-v2": AdapterSpec(
        "satoshi-hunt-native-btc-quick-v2", "bounded-escrow-preimage-v1", "COMPUTE",
        "p2wsh-sha256-preimage", "RUNNABLE", "0..1048575 nonce range",
        "0..1048575", "challenge_adapters.bounded_escrow_preimage:solve",
        ({"challenge_id":"satoshi-hunt-native-btc-quick-v2","difficulty_bits":16,"max_nonce":1048575,"known_nonce":10697,"known_hash":"0000085f05d9cf7c4c2d14ec2a07ad67c0c5e58177c128ba81eca68fdf556c19"},),
        "Permissionless P2WSH escrow. Requires exact on-chain funding before marketplace promotion.",
    ),
    "satoshi-hunt-native-btc-hard-v2": AdapterSpec(
        "satoshi-hunt-native-btc-hard-v2", "bounded-escrow-preimage-v1", "COMPUTE",
        "p2wsh-sha256-preimage", "RUNNABLE", "0..4194303 nonce range",
        "0..4194303", "challenge_adapters.bounded_escrow_preimage:solve",
        ({"challenge_id":"satoshi-hunt-native-btc-hard-v2","difficulty_bits":20,"max_nonce":4194303,"known_nonce":584976,"known_hash":"000004da13ee3ef33c5fab1a177e2ea796bf868fc8e006b17e97399291388cdf"},),
        "Permissionless P2WSH escrow. Requires exact on-chain funding before marketplace promotion.",
    ),
    "satoshi-hunt-native-btc-extreme-v2": AdapterSpec(
        "satoshi-hunt-native-btc-extreme-v2", "bounded-escrow-preimage-v1", "COMPUTE",
        "p2wsh-sha256-preimage", "RUNNABLE", "0..16777215 nonce range",
        "0..16777215", "challenge_adapters.bounded_escrow_preimage:solve",
        ({"challenge_id":"satoshi-hunt-native-btc-extreme-v2","difficulty_bits":24,"max_nonce":16777215,"known_nonce":14248268,"known_hash":"00000091bf9339f832c656d243fa3fc5f6c1f1e06127bb68d0eeea8fa30013c8"},),
        "Permissionless P2WSH escrow. Requires exact on-chain funding before marketplace promotion.",
    ),
    "base-leading-zero-canary": AdapterSpec(
        "base-leading-zero-canary", "bounded-leading-zero-v1", "COMPUTE",
        "leading-zero-proof", "RUNNABLE", "finite nonce range",
        "0..max_nonce declared by challenge",
        "challenge_adapters.bounded_leading_zero:solve",
        (
            {"challenge": "satoshi-hunt-test", "difficulty_bits": 8, "max_nonce": 100000},
        ),
        "Only eligible when a public reward registry record explicitly binds this adapter to a funded, permissionless, deterministic verifier. The adapter itself does not claim or settle funds.",
    ),
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
    "aoi-nakamoto-quizchain-0-854btc": AdapterSpec(
        "aoi-nakamoto-quizchain-0-854btc", "md5-bip39-bip44-v1",
        "RESEARCH", "md5-to-bip39-p2pkh", "VERIFIED",
        "author source-text serialization is not bounded",
        None, None,
        ({"oracle": "published-md5-to-bip39-calibration", "derivation": "m/44'/0'/0'/0/i", "indices": [0,1,2,3,4,5]},),
        "Real Big Block is a funded public 0.777 BTC escrow, but the exact source bytes/twist are unresolved. Do not run generic brute force or claim a bounded solver.",
    ),
    "genesis-block-wallet-puzzle-142ksats": AdapterSpec(
        "genesis-block-wallet-puzzle-142ksats", "genesis-p2wsh-bip48-v1",
        "RESEARCH", "p2wsh-2of2-derivation", "VERIFIED",
        "passphrase/candidate interpretation is not bounded",
        None, None,
        ({"oracle": "certified-p2wsh-2of2", "witness_program": "4dae67a9872f1402109f9670276afc2c0758f895aafddcd089795771b796483"},),
        "Funded public P2WSH challenge with a certified offline oracle, but the remaining passphrase/source interpretation is not a bounded public compute domain.",
    ),
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
        "adapter_audited": spec.audited,
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
