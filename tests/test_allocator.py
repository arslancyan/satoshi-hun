from allocator import allocate_ranges, validate_non_overlapping

def test_allocator_covers_space_without_overlap():
    ranges = allocate_ranges(0, 100, 7)
    assert ranges[0]["start"] == 0
    assert ranges[-1]["end"] == 100
    assert sum(r["end"] - r["start"] for r in ranges) == 100
    assert validate_non_overlapping(ranges)

def test_allocator_is_deterministic():
    assert allocate_ranges(10, 23, 4) == allocate_ranges(10, 23, 4)

def test_allocator_rejects_invalid_space():
    try:
        allocate_ranges(10, 10, 2)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid range must be rejected")


def test_weighted_allocator_covers_space_without_overlap():
    from allocator import allocate_weighted_ranges
    ranges = allocate_weighted_ranges(
        0, 100,
        [{"id": "slow", "score": 1}, {"id": "fast", "score": 3}, {"id": "mid", "score": 2}],
    )
    assert ranges[0]["start"] == 0
    assert ranges[-1]["end"] == 100
    assert sum(r["end"] - r["start"] for r in ranges) == 100
    assert validate_non_overlapping(ranges)
    assert all(r["end"] > r["start"] for r in ranges)

def test_weighted_allocator_is_stable_for_equal_inputs():
    workers = [{"id": "b", "score": 2}, {"id": "a", "score": 1}]
    from allocator import allocate_weighted_ranges
    assert allocate_weighted_ranges(0, 17, workers) == allocate_weighted_ranges(0, 17, workers)
