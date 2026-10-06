"""Anti-cheat primitives for Satoshi Hunt.

These checks protect accounting integrity without inspecting private keys,
wallet credentials, or unrelated user data.
"""
import hashlib
import json


def fingerprint_assignment(job_id, worker_id, start, end):
    payload = {"job_id": str(job_id), "worker_id": str(worker_id), "start": int(start), "end": int(end)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def detect_range_overlap(ranges):
    ordered = sorted(ranges, key=lambda x: (int(x["start"]), int(x["end"])))
    overlaps = []
    for left, right in zip(ordered, ordered[1:]):
        if int(left["end"]) > int(right["start"]):
            overlaps.append((left, right))
    return overlaps


def validate_proof_sequence(proofs):
    ordered = sorted(proofs, key=lambda x: x["created_at"])
    seen = set()
    for proof in ordered:
        key = (str(proof["assignment_id"]), str(proof["proof_hash"]))
        if key in seen:
            return False
        seen.add(key)
        if int(proof.get("cpu_seconds", 0)) < 0:
            return False
    return True


def security_flags(claim_count, duplicate_count, rejected_count, stale_count):
    flags = []
    if duplicate_count > max(3, claim_count * 0.2):
        flags.append("HIGH_DUPLICATE_RATE")
    if rejected_count > max(5, claim_count * 0.3):
        flags.append("HIGH_REJECTION_RATE")
    if stale_count > max(5, claim_count * 0.2):
        flags.append("HIGH_STALE_RATE")
    return flags
