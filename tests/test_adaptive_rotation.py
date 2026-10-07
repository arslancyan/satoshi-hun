from adaptive_rotation import freshness_score, opportunity_score, rank_challenges


def record(id, probability, reward, workers=0, action_ready=True):
    return {
        "id": id,
        "status": "OPEN + FUNDED",
        "balance_btc": reward,
        "reward_btc": reward,
        "live_checked_at": "2026-10-07T00:00:00+00:00",
        "verification": {
            "funding_match": True,
            "execution_mode": "COMPUTE" if action_ready else "RESEARCH",
            "adapter_runnable": action_ready,
            "adapter_audited": action_ready,
        },
        "search_metrics": {
            "probability_24h": probability,
            "active_workers": workers,
            "reliability": 1.0,
            "measured_at": "2026-10-07T00:00:00+00:00",
            "exhaustion_hours": 24.0,
        },
    }


def test_opportunity_score_rewards_probability_over_raw_reward():
    high_probability = record("likely", 0.2, 1.0)
    huge_reward = record("huge", 0.000001, 100.0)
    assert opportunity_score(high_probability) > opportunity_score(huge_reward)


def test_rotation_queue_only_contains_runnable_compute_targets():
    result = rank_challenges([
        record("research", 0.9, 9.0, action_ready=False),
        record("compute", 0.1, 1.0, action_ready=True),
    ])
    assert [x["id"] for x in result["queue"]] == ["compute"]


def test_rotation_is_limited_to_requested_display_size():
    rows = [record(str(i), 0.01, 1.0) for i in range(35)]
    result = rank_challenges(rows, limit=30, queue_limit=30)
    assert len(result["ranked"]) == 30


def test_freshness_never_exceeds_one():
    assert 0.0 <= freshness_score(record("x", 0.1, 1.0)) <= 1.0
