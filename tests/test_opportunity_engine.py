from opportunity_engine import build_opportunity_metrics, competition_score, funding_confidence


def test_funding_confidence():
    assert funding_confidence(1.0, 1.0, True, False) == 1.0
    assert funding_confidence(1.0, 1.0, True, True) == 0.0


def test_competition_penalty():
    assert competition_score(1, 0.1) > competition_score(100, 100.0)


def test_opportunity_score_is_bounded():
    record = {
        "reward_btc": 0.5,
        "balance_btc": 0.5,
        "verification": {
            "advertised_reward_btc": 0.5,
            "verified_balance_btc": 0.5,
            "funding_match": True,
            "verification_stale": False,
            "oracle_certified": True,
            "execution_mode": "COMPUTE",
            "leads": ["bounded"],
            "checked_at": "2099-01-01T00:00:00+00:00",
        },
        "search_metrics": {
            "probability_24h": 0.02,
            "reliability": 0.9,
            "active_workers": 1,
            "attempts_per_second": 0.1,
            "measured_at": "2099-01-01T00:00:00+00:00",
        },
    }
    result = build_opportunity_metrics(record)
    assert 0.0 <= result["opportunity_score"] <= 1.0
    assert result["funding_confidence"] == 1.0
