"""Measured worker telemetry helpers.

Only server-observed activity is aggregated here. Candidate submission rate
is kept separate from any cryptographic attempt rate.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Iterable
from expected_value import build_search_metrics, expected_value_score


def _time(v: Any):
    if not v:
        return None
    if isinstance(v, datetime):
        d = v
    else:
        try:
            d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def active_worker_count(rows: Iterable[dict[str, Any]], *, now: datetime, heartbeat_timeout_seconds: float = 120.0) -> int:
    cutoff = now.timestamp() - max(1.0, float(heartbeat_timeout_seconds))
    ids = set()
    for r in rows:
        if str(r.get("assignment_status", "")).upper() != "RUNNING":
            continue
        hb = _time(r.get("last_heartbeat_at") or r.get("worker_last_seen_at"))
        if hb and hb.timestamp() >= cutoff:
            ids.add(str(r.get("worker_id")))
    return len(ids)


def verified_seconds(rows: Iterable[dict[str, Any]], *, now: datetime) -> int:
    total = 0
    for r in rows:
        stored = max(0, int(r.get("verified_seconds") or 0))
        started = _time(r.get("started_at") or r.get("assigned_at"))
        hb = _time(r.get("last_heartbeat_at") or r.get("worker_last_seen_at"))
        if str(r.get("assignment_status", "")).upper() == "RUNNING" and started and hb:
            stored = max(stored, int(max(0, (min(now, hb) - started).total_seconds())))
        total += stored
    return total


def claim_rate(count: int, window_seconds: float) -> float:
    return max(0, int(count)) / max(1.0, float(window_seconds))


def telemetry_metrics(*, keyspace_total: int | None = None, keyspace_searched: int = 0,
                      measured_attempts_per_second: float | None = None, active_workers: int = 0,
                      verified_seconds_value: int = 0, claims: int = 0, window_seconds: float = 3600.0,
                      reward_btc: float = 0.0, reliability: float = 1.0, measured_at: str | None = None) -> dict[str, Any]:
    rate = float(measured_attempts_per_second or 0.0)
    metrics = {
        "telemetry_source": "worker_telemetry",
        "telemetry_window_seconds": int(max(1, window_seconds)),
        "active_workers": max(0, int(active_workers)),
        "verified_seconds": max(0, int(verified_seconds_value)),
        "claim_count": max(0, int(claims)),
        "observed_claims_per_second": round(claim_rate(claims, window_seconds), 9),
        "attempt_rate_semantics": "audited_attempt_counter" if rate > 0 else "unrated",
        "attempts_per_second": round(rate, 6) if rate > 0 else 0.0,
        "reliability": max(0.0, min(1.0, float(reliability))),
        "measured_at": measured_at or datetime.now(timezone.utc).isoformat(),
    }
    if keyspace_total and int(keyspace_total) > 0:
        metrics.update(build_search_metrics(
            keyspace_total=int(keyspace_total), keyspace_searched=max(0, int(keyspace_searched)),
            attempts_per_second=rate, active_workers=active_workers, reward_btc=reward_btc,
            measured_at=metrics["measured_at"],
        ))
        metrics["telemetry_source"] = "worker_telemetry"
        metrics["telemetry_window_seconds"] = int(max(1, window_seconds))
        metrics["verified_seconds"] = max(0, int(verified_seconds_value))
        metrics["claim_count"] = max(0, int(claims))
        metrics["observed_claims_per_second"] = round(claim_rate(claims, window_seconds), 9)
        metrics["attempt_rate_semantics"] = "audited_attempt_counter" if rate > 0 else "unrated"
        metrics["reliability"] = max(0.0, min(1.0, float(reliability)))
    else:
        metrics.update({
            "keyspace_total": None, "keyspace_searched": None, "keyspace_remaining": None,
            "coverage_pct": None, "exhaustion_hours": None, "probability_observed": 0.0,
            "probability_24h": 0.0, "difficulty_category": "UNRATED",
            "probability_model": "unrated_without_measurable_search_space",
            "reward_btc": max(0.0, float(reward_btc)),
        })
    metrics["expected_value_score"] = expected_value_score(
        metrics.get("reward_btc", reward_btc), metrics.get("probability_24h", 0.0),
        metrics.get("exhaustion_hours"), reliability=metrics["reliability"],
    )
    return metrics


def collect_from_rows(rows: Iterable[dict[str, Any]], *, now: datetime | None = None,
                      heartbeat_timeout_seconds: float = 120.0, reward_btc: float = 0.0,
                      claim_window_seconds: float = 3600.0, keyspace_total: int | None = None,
                      keyspace_searched: int = 0, measured_attempts_per_second: float | None = None,
                      reliability: float = 1.0) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    rows = list(rows)
    return telemetry_metrics(
        keyspace_total=keyspace_total, keyspace_searched=keyspace_searched,
        measured_attempts_per_second=measured_attempts_per_second,
        active_workers=active_worker_count(rows, now=now, heartbeat_timeout_seconds=heartbeat_timeout_seconds),
        verified_seconds_value=verified_seconds(rows, now=now),
        claims=sum(max(0, int(r.get("claim_count") or 0)) for r in rows),
        window_seconds=claim_window_seconds, reward_btc=reward_btc, reliability=reliability,
        measured_at=now.isoformat(),
    )
