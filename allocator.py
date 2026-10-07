"""Deterministic, non-overlapping work allocation primitives.

Adapters decide the candidate-space semantics. This module only partitions a
declared integer search space and never accesses wallets, private keys, or
credentials.
"""

def allocate_ranges(start: int, end: int, workers: int):
    if start < 0 or end <= start or workers < 1:
        raise ValueError("invalid allocation bounds")
    total = end - start
    workers = min(workers, total)
    base, remainder = divmod(total, workers)
    ranges = []
    cursor = start
    for i in range(workers):
        size = base + (1 if i < remainder else 0)
        nxt = cursor + size
        ranges.append({"index": i, "start": cursor, "end": nxt})
        cursor = nxt
    return ranges

def validate_non_overlapping(ranges):
    ordered = sorted(ranges, key=lambda x: x["start"])
    return all(a["end"] <= b["start"] for a, b in zip(ordered, ordered[1:]))


def allocate_weighted_ranges(start: int, end: int, workers):
    """Deterministically partition a bounded space by worker scores.

    Every range is half-open [start, end), covers the requested space exactly,
    and gives each active worker at least one candidate when capacity allows.
    """
    if start < 0 or end <= start or not workers:
        raise ValueError("invalid allocation bounds or workers")
    ordered = sorted(
        workers,
        key=lambda w: (float(w.get("score", 1.0)), str(w.get("id", ""))),
        reverse=True,
    )
    count = min(len(ordered), end - start)
    ordered = ordered[:count]
    weights = [max(0.1, float(w.get("score", 1.0))) for w in ordered]
    total = end - start
    base = total // count
    extra = total % count
    ranges = []
    cursor = start
    for i, (worker, weight) in enumerate(zip(ordered, weights)):
        remaining = count - i - 1
        target = base + (1 if i < extra else 0)
        if i < count - 1:
            weighted = max(1, round(total * weight / sum(weights)))
            target = min(max(1, weighted), total - cursor - remaining)
        nxt = end if i == count - 1 else cursor + target
        ranges.append({"worker_id": str(worker["id"]), "start": cursor, "end": nxt})
        cursor = nxt
        total = end - cursor
        weights = weights[i + 1:]
    return ranges
