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
