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


def reputation_score(claim_count, verified_count, rejected_count, stale_count, completed_count, total_seconds):
    """Return a conservative 0-100 worker score from server-observed activity.

    Unproven client claims never increase the score. Negative signals are
    weighted more strongly than positive signals, and small samples remain
    close to the neutral baseline.
    """
    claim_count=max(0,int(claim_count))
    verified_count=max(0,int(verified_count))
    rejected_count=max(0,int(rejected_count))
    stale_count=max(0,int(stale_count))
    completed_count=max(0,int(completed_count))
    total_seconds=max(0,int(total_seconds))

    positive=verified_count*4 + completed_count*1.0 + min(total_seconds/3600.0,1000)*0.01
    negative=rejected_count*6 + stale_count*4
    raw=50.0 + positive - negative

    flags=security_flags(claim_count, max(0, claim_count-verified_count-rejected_count), rejected_count, stale_count)
    if "HIGH_DUPLICATE_RATE" in flags:
        raw -= 10
    if "HIGH_REJECTION_RATE" in flags:
        raw -= 15
    if "HIGH_STALE_RATE" in flags:
        raw -= 10

    # Do not let a tiny sample create an extreme reputation.
    sample=min(1.0, claim_count/20.0)
    score=50.0 + (raw-50.0)*sample
    return round(max(0.0,min(100.0,score)),2)
