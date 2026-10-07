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
    capacity = end - start
    count = min(len(ordered), capacity)
    ordered = ordered[:count]

    weights = [max(0.1, float(w.get("score", 1.0))) for w in ordered]
    total_weight = sum(weights)
    remaining = capacity - count
    raw_extra = [
        (remaining * weight / total_weight) if total_weight else 0.0
        for weight in weights
    ]
    extras = [int(value) for value in raw_extra]
    leftover = remaining - sum(extras)

    order = sorted(
        range(count),
        key=lambda i: (raw_extra[i] - extras[i], str(ordered[i]["id"])),
        reverse=True,
    )
    for i in order[:leftover]:
        extras[i] += 1

    ranges = []
    cursor = start
    for worker, extra in zip(ordered, extras):
        size = 1 + extra
        nxt = cursor + size
        ranges.append(
            {"worker_id": str(worker["id"]), "start": cursor, "end": nxt}
        )
        cursor = nxt
    return ranges
