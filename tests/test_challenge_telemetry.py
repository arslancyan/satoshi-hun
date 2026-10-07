from datetime import datetime, timezone, timedelta

from challenge_telemetry import active_worker_count, claim_rate, collect_from_rows, telemetry_metrics, verified_seconds

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def row(worker, status="RUNNING", heartbeat=None, started=None, claims=0):
    return {
        "worker_id": worker,
        "assignment_status": status,
        "last_heartbeat_at": heartbeat or NOW.isoformat(),
        "worker_last_seen_at": heartbeat or NOW.isoformat(),
        "started_at": started or (NOW - timedelta(seconds=60)).isoformat(),
        "assigned_at": started or (NOW - timedelta(seconds=60)).isoformat(),
        "verified_seconds": 0,
        "claim_count": claims,
    }


def test_active_workers_excludes_stale_and_deduplicates():
    rows = [row("w1"), row("w2", heartbeat=(NOW - timedelta(minutes=5)).isoformat()), row("w3"), row("w1")]
    assert active_worker_count(rows, now=NOW, heartbeat_timeout_seconds=120) == 2


def test_verified_seconds_uses_server_observed_window():
    rows = [row("w1", started=(NOW - timedelta(seconds=90)).isoformat())]
    assert verified_seconds(rows, now=NOW) == 90


def test_claim_rate_is_not_attempt_rate():
    assert claim_rate(30, 60) == 0.5
    metrics = telemetry_metrics(claims=30, window_seconds=60)
    assert metrics["observed_claims_per_second"] == 0.5
    assert metrics["attempts_per_second"] == 0.0
    assert metrics["attempt_rate_semantics"] == "unrated"


def test_probability_stays_unrated_without_search_space():
    metrics = collect_from_rows([row("w1", claims=10)], now=NOW, reward_btc=1.0)
    assert metrics["active_workers"] == 1
    assert metrics["probability_24h"] == 0.0
    assert metrics["difficulty_category"] == "UNRATED"
    assert metrics["exhaustion_hours"] is None
    assert metrics["expected_value_score"] == 0.0


def test_audited_attempt_counter_can_drive_probability():
    metrics = collect_from_rows(
        [row("w1", claims=10)],
        now=NOW,
        keyspace_total=1_000_000,
        keyspace_searched=100_000,
        measured_attempts_per_second=100.0,
        reward_btc=1.0,
    )
    assert metrics["attempt_rate_semantics"] == "audited_attempt_counter"
    assert metrics["attempts_per_second"] == 100.0
    assert metrics["probability_24h"] > 0
    assert metrics["keyspace_remaining"] == "900000"
