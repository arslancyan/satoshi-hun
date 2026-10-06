"""Satoshi Hunt Protocol v1 primitives.

Safe coordination only: declared public challenge search spaces, worker capability
matching, deterministic allocation and proof hashing. No wallet/private-key work.
"""
from hashlib import sha256
import json


def capability_score(worker, required=None):
    required = required or {}
    threads = max(1, int(worker.get("cpu_threads", 1)))
    required_threads = max(1, int(required.get("cpu_threads", 1)))
    score = min(1.0, threads / required_threads)
    adapters = set(worker.get("adapter_types", []))
    needed = set(required.get("adapter_types", []))
    if needed and not needed.issubset(adapters):
        return 0.0
    return round(score, 6)


def adaptive_ranges(start, end, workers):
    if start < 0 or end <= start or not workers:
        raise ValueError("invalid search space or workers")
    ranked = sorted(workers, key=lambda w: (float(w.get("score", 1.0)), str(w.get("id", ""))), reverse=True)
    weights = [max(0.1, float(w.get("score", 1.0))) for w in ranked]
    total = end - start
    weight_sum = sum(weights)
    ranges = []
    cursor = start
    for i, (worker, weight) in enumerate(zip(ranked, weights)):
        remaining_workers = len(ranked) - i
        if i == len(ranked) - 1:
            nxt = end
        else:
            size = max(1, int(total * weight / weight_sum))
            max_allowed = end - cursor - (remaining_workers - 1)
            nxt = cursor + min(size, max_allowed)
        ranges.append({"worker_id": str(worker["id"]), "start": cursor, "end": nxt})
        cursor = nxt
        total = end - cursor
        weight_sum -= weight
    return ranges


def proof_hash(job_id, assignment_id, cursor_start, cursor_end, cursor_next, nonce=""):
    payload = {
        "job_id": str(job_id),
        "assignment_id": str(assignment_id),
        "cursor_start": int(cursor_start),
        "cursor_end": int(cursor_end),
        "cursor_next": int(cursor_next),
        "nonce": str(nonce),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(canonical).hexdigest()


def verify_checkpoint(checkpoint):
    return (
        int(checkpoint["cursor_start"]) <= int(checkpoint["cursor_next"]) <= int(checkpoint["cursor_end"])
        and int(checkpoint["cursor_end"]) > int(checkpoint["cursor_start"])
        and bool(checkpoint.get("checkpoint_hash"))
    )


def reliability_score(verified, rejected, stale, completed, total_seconds):
    positive = verified * 3 + completed + min(total_seconds / 3600.0, 1000) * 0.01
    negative = rejected * 4 + stale * 2
    return round(max(0.0, min(100.0, 50.0 + positive - negative)), 2)
