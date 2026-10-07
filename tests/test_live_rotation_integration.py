from pathlib import Path


def test_live_source_worker_uses_adaptive_rotation_not_static_priority_list():
    source = Path("live_source_worker.py").read_text()
    assert "rank_challenges(registry_records)" in source
    assert "_refresh_telemetry(cur, records)" in source
    assert "PRIORITY_BTC_CHALLENGES" not in source
    assert "order by expected_value_score desc" in source
