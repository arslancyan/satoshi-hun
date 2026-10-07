"""Deterministic audit for challenge adapter promotion.

This audit never promotes a challenge by itself. It classifies catalog entries
as DISCOVERED, VERIFIED, AUDITED, or RUNNABLE from the checked-in adapter contract and
fails when an AUDITED/RUNNABLE adapter is incomplete or its known test vector is wrong.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any

from challenge_adapters import ADAPTERS, AdapterSpec


EXPECTED_DIGESTS = {
    ("sha256", "satoshi-hunt:0"): "65a68da3e9455fd096284e595aa18116e5e49d92671f35d97719d8f484c3fc0a",
    ("ripemd160", "satoshi-hunt:0"): "660b4d759de0b70b4f4ccd75213791ebe838f93b",
    ("hash160", "satoshi-hunt:0"): "bdf2f3fa94e2b54e27a79f1a5495f4389db023bc",
    ("hash256", "satoshi-hunt:0"): "f6da5a96c8dbd72a0d9d9a02a81387fa58931336ef457b027b6f4a12955815ef",
}


def _digest(algorithm: str, message: bytes) -> bytes:
    if algorithm == "sha256":
        return hashlib.sha256(message).digest()
    if algorithm == "ripemd160":
        return hashlib.new("ripemd160", message).digest()
    if algorithm == "hash160":
        return hashlib.new("ripemd160", hashlib.sha256(message).digest()).digest()
    if algorithm == "hash256":
        return hashlib.sha256(hashlib.sha256(message).digest()).digest()
    raise ValueError(f"unsupported algorithm: {algorithm}")


def _expected(algorithm: str, message: str) -> str:
    return _digest(algorithm, message.encode()).hex()


def _resolve_entrypoint(entrypoint: str):
    module_name, function_name = entrypoint.split(":", 1)
    return getattr(importlib.import_module(module_name), function_name)


def audit_adapter(spec: AdapterSpec) -> list[str]:
    errors: list[str] = []
    if spec.status in {"AUDITED", "RUNNABLE"}:
        if spec.execution_mode != "COMPUTE":
            errors.append("AUDITED/RUNNABLE adapter must use COMPUTE execution_mode")
        if not spec.search_space:
            errors.append("AUDITED/RUNNABLE adapter must declare a bounded search_space")
        if not spec.solver_entrypoint:
            errors.append("AUDITED/RUNNABLE adapter must declare solver_entrypoint")
        if not spec.test_vectors:
            errors.append("AUDITED/RUNNABLE adapter must declare test_vectors")

        if spec.solver_entrypoint:
            try:
                verifier = _resolve_entrypoint(spec.solver_entrypoint)
            except Exception as exc:
                errors.append(f"solver_entrypoint import failed: {exc}")
            else:
                for vector in spec.test_vectors:
                    if {"algorithm", "message"} <= set(vector):
                        algorithm = str(vector.get("algorithm", "")).lower()
                        message = str(vector.get("message", ""))
                        if not algorithm or not message:
                            errors.append("audited/runnable test vector needs algorithm and message")
                            continue
                        expected = EXPECTED_DIGESTS.get((algorithm, message))
                        if expected is None:
                            errors.append(f"no pinned expected digest for {algorithm}:{message}")
                            continue
                        result = verifier(algorithm, message.encode()).hex()
                        if result != expected:
                            errors.append(
                                f"test vector mismatch for {algorithm}:{message}: "
                                f"{result} != {expected}"
                            )
                    elif {"challenge", "difficulty_bits", "max_nonce"} <= set(vector):
                        challenge = str(vector["challenge"])
                        difficulty = int(vector["difficulty_bits"])
                        max_nonce = int(vector["max_nonce"])
                        if max_nonce < 0 or max_nonce > 10_000_000:
                            errors.append("bounded PoW test vector max_nonce must be finite and <= 10,000,000")
                            continue
                        try:
                            solved = verifier(challenge, difficulty, max_nonce, max_attempts=max_nonce + 1)
                        except Exception as exc:
                            errors.append(f"bounded PoW vector execution failed: {exc}")
                            continue
                        if not solved:
                            errors.append("bounded PoW test vector did not produce a solution")
                            continue
                        if int(solved["nonce"]) > max_nonce:
                            errors.append("bounded PoW solver returned nonce outside declared range")
                            continue
                        from challenge_adapters.bounded_leading_zero import verify as verify_bounded
                        checked = verify_bounded(
                            challenge, difficulty, int(solved["nonce"]), str(solved["hash"]), max_nonce
                        )
                        if not checked.get("valid"):
                            errors.append("bounded PoW test vector failed independent verifier")
                    else:
                        errors.append("unsupported audited/runnable test vector schema")
        return errors

    if spec.execution_mode == "COMPUTE":
        errors.append("non-RUNNABLE COMPUTE adapter must not be treated as runnable")
    return errors


def classify(challenge_id: str) -> str:
    spec = ADAPTERS.get(challenge_id)
    if spec is None:
        return "DISCOVERED"
    if spec.status == "RUNNABLE" and spec.runnable:
        return "RUNNABLE"
    if spec.status == "AUDITED":
        return "AUDITED"
    return "VERIFIED" if spec.status == "VERIFIED" else spec.status


def main(argv: list[str]) -> int:
    catalog_path = Path(argv[1]) if len(argv) > 1 else None
    catalog: list[dict[str, Any]] = []
    if catalog_path:
        payload = json.loads(catalog_path.read_text())
        catalog = payload.get("puzzles", [])

    failures: list[str] = []
    for spec in ADAPTERS.values():
        failures.extend(
            f"{spec.challenge_id}: {error}"
            for error in audit_adapter(spec)
        )

    report = {
        "adapter_count": len(ADAPTERS),
        "catalog_count": len(catalog),
        "statuses": {},
        "failures": failures,
    }

    ids = [str(item.get("id")) for item in catalog if item.get("id") is not None]
    for challenge_id in ids:
        report["statuses"][challenge_id] = classify(challenge_id)

    for challenge_id, spec in ADAPTERS.items():
        report["statuses"][challenge_id] = classify(challenge_id)

    print(json.dumps(report, indent=2, sort_keys=True))
    if failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
