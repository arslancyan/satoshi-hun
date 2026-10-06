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
