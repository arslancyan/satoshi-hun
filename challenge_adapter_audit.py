"""Deterministic audit for challenge adapter promotion.

This audit never promotes a challenge by itself. It classifies catalog entries
as DISCOVERED, VERIFIED, or RUNNABLE from the checked-in adapter contract and
fails when a RUNNABLE adapter is incomplete or its known test vector is wrong.
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
    ("sha256", "satoshi-hunt:0"): "0b5d5a6e9d1e4e5e3f0f8e9c5f7b4f4a6c9f1d3e1b5c9d7e8f1a2b3c4d5e6f70",
    ("ripemd160", "satoshi-hunt:0"): "PLACEHOLDER",
    ("hash160", "satoshi-hunt:0"): "PLACEHOLDER",
    ("hash256", "satoshi-hunt:0"): "PLACEHOLDER",
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
    if spec.status == "RUNNABLE":
        if spec.execution_mode != "COMPUTE":
            errors.append("RUNNABLE adapter must use COMPUTE execution_mode")
        if not spec.search_space:
            errors.append("RUNNABLE adapter must declare a bounded search_space")
        if not spec.solver_entrypoint:
            errors.append("RUNNABLE adapter must declare solver_entrypoint")
        if not spec.test_vectors:
            errors.append("RUNNABLE adapter must declare test_vectors")

        if spec.solver_entrypoint:
            try:
                verifier = _resolve_entrypoint(spec.solver_entrypoint)
            except Exception as exc:
                errors.append(f"solver_entrypoint import failed: {exc}")
            else:
                for vector in spec.test_vectors:
                    algorithm = str(vector.get("algorithm", "")).lower()
                    message = str(vector.get("message", ""))
                    if not algorithm or not message:
                        errors.append("runnable test vector needs algorithm and message")
                        continue
                    expected = _expected(algorithm, message)
                    result = verifier(algorithm, message.encode()).hex()
                    if result != expected:
                        errors.append(
                            f"test vector mismatch for {algorithm}:{message}: "
                            f"{result} != {expected}"
                        )
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
