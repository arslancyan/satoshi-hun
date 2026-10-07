from strategy_router import choose_strategy, rank_targets

def base_record(mode="RUN", runnable=True, probability=0.1, hours=10):
    return {
        "id": "x", "title": "X", "reward_btc": 1,
        "verification": {"execution_mode": mode, "adapter_runnable": runnable},
        "search_metrics": {"probability_24h": probability, "exhaustion_hours": hours}
    }

def test_unrunnable_is_research():
    d = choose_strategy(base_record(mode="RESEARCH", runnable=False))
    assert d.action == "RESEARCH"

def test_low_probability_is_pause():
    d = choose_strategy(base_record(probability=0))
    assert d.action == "PAUSE"

def test_verified_positive_ev_is_run():
    d = choose_strategy(base_record())
    assert d.action == "RUN"

def test_rank_prioritizes_runnable_targets():
    rows = rank_targets([base_record(mode="RESEARCH", runnable=False), base_record()])
    assert rows[0]["strategy"]["action"] == "RUN"
