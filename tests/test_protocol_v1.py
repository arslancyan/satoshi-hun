from protocol_v1 import adaptive_ranges, capability_score, economic_priority, proof_hash, reliability_score
from anti_cheat import detect_range_overlap, fingerprint_assignment, security_flags


def test_adaptive_ranges_cover_without_overlap():
    workers=[{"id":"a","score":1},{"id":"b","score":2},{"id":"c","score":1}]
    ranges=adaptive_ranges(0,100,workers)
    assert ranges[0]["start"] == 0
    assert ranges[-1]["end"] == 100
    assert not detect_range_overlap(ranges)


def test_capability_matching_rejects_missing_adapter():
    assert capability_score({"cpu_threads":4,"adapter_types":["x"]},{"adapter_types":["y"]}) == 0


def test_proof_hash_is_deterministic():
    a=proof_hash("j","a",0,100,50,"n")
    b=proof_hash("j","a",0,100,50,"n")
    assert a == b and len(a) == 64


def test_reliability_score_is_bounded():
    assert 0 <= reliability_score(100,0,0,100,100000) <= 100
    assert 0 <= reliability_score(0,100,100,0,0) <= 100


def test_security_flags_detect_abuse_patterns():
    flags=security_flags(10,8,0,0)
    assert "HIGH_DUPLICATE_RATE" in flags


def test_assignment_fingerprint_changes_with_range():
    a=fingerprint_assignment("j","w",0,10)
    b=fingerprint_assignment("j","w",10,20)
    assert a != b


def test_economic_priority_prefers_higher_expected_reward_per_hour():
    high = economic_priority(0.01, 3600, 0.10, 1.0)
    low = economic_priority(0.02, 7200, 0.01, 1.0)
    assert high > low


def test_economic_priority_is_bounded_for_bad_inputs():
    assert economic_priority(-1, 0, 5, 5) == 0.0
