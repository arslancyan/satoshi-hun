from expected_value import (
    birthday_collision_probability, build_search_metrics, classify_difficulty,
    expected_value_score, keyspace_width, uniform_success_probability,
)

def test_keyspace_width_uses_inclusive_bounds():
    assert keyspace_width(2**70, 2**71 - 1) == 2**70

def test_probability_is_bounded():
    assert uniform_success_probability(100, 10, 5) == 0.5
    assert uniform_success_probability(100, 1000, 5) == 1.0

def test_metrics_are_integer_safe_and_rankable():
    m = build_search_metrics(keyspace_total=2**70, keyspace_searched=2**69,
                             attempts_per_second=1_000_000, active_workers=4, reward_btc=7.1)
    assert m["keyspace_remaining"] == str(2**69)
    assert m["coverage_pct"] == 50.0
    assert m["difficulty_category"] == "EXTREME"
    assert 0 < m["probability_24h"] < 1

def test_difficulty_thresholds():
    assert classify_difficulty(1) == "QUICK"
    assert classify_difficulty(24 * 30) == "HARD"
    assert classify_difficulty(24 * 30 + 1) == "EXTREME"
    assert classify_difficulty(None) == "UNRATED"

def test_collision_probability_increases_with_samples():
    assert birthday_collision_probability(100, 32) < birthday_collision_probability(1000, 32)

def test_expected_value_score_is_conservative():
    assert expected_value_score(10, 0.5, 10) == 0.5
    assert expected_value_score(10, 0.5, None) == 0.0
