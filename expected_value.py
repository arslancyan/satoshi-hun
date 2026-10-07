"""Public challenge expected-value and runtime-metrics helpers.

Analytics only: this module does not derive private keys, scan wallet
keyspaces, or submit blockchain transactions. It ranks already-declared public
challenge metrics.
"""
from __future__ import annotations
from datetime import datetime, timezone
from math import exp
from typing import Any

DIFFICULTY_THRESHOLDS_HOURS = {"QUICK": 24.0, "HARD": 24.0 * 30.0}

def keyspace_width(start: int, end: int, inclusive: bool = True) -> int:
    start, end = int(start), int(end)
    if start < 0 or end < start:
        raise ValueError("invalid keyspace bounds")
    width = end - start + (1 if inclusive else 0)
    if width <= 0:
        raise ValueError("keyspace must contain at least one candidate")
    return width

def estimate_exhaustion_hours(remaining: int, attempts_per_second: float) -> float | None:
    remaining = max(0, int(remaining))
    rate = float(attempts_per_second)
    if remaining == 0:
        return 0.0
    if rate <= 0:
        return None
    return remaining / rate / 3600.0

def uniform_success_probability(remaining: int, attempts_per_second: float, horizon_seconds: float) -> float:
    remaining = max(0, int(remaining))
    rate = max(0.0, float(attempts_per_second))
    horizon = max(0.0, float(horizon_seconds))
    if remaining == 0:
        return 1.0
    if rate <= 0 or horizon <= 0:
        return 0.0
    return min(1.0, (rate * horizon) / remaining)

def birthday_collision_probability(samples: int, digest_bits: int) -> float:
    samples = max(0, int(samples))
    digest_bits = int(digest_bits)
    if digest_bits <= 0:
        raise ValueError("digest_bits must be positive")
    if samples < 2:
        return 0.0
    exponent = (samples * (samples - 1)) / (2.0 * (2.0 ** digest_bits))
    if exponent >= 50:
        return 1.0
    return 1.0 - exp(-exponent)

def classify_difficulty(exhaustion_hours: float | None) -> str:
    if exhaustion_hours is None:
        return "UNRATED"
    if exhaustion_hours <= DIFFICULTY_THRESHOLDS_HOURS["QUICK"]:
        return "QUICK"
    if exhaustion_hours <= DIFFICULTY_THRESHOLDS_HOURS["HARD"]:
        return "HARD"
    return "EXTREME"

def build_search_metrics(*, keyspace_total: int, keyspace_searched: int = 0,
                         attempts_per_second: float = 0.0, active_workers: int = 0,
                         reward_btc: float = 0.0, horizon_seconds: float = 86400.0,
                         measured_at: str | None = None,
                         probability_model: str = "uniform_remaining_candidate") -> dict[str, Any]:
    total = max(1, int(keyspace_total))
    searched = min(max(0, int(keyspace_searched)), total)
    remaining = total - searched
    rate = max(0.0, float(attempts_per_second))
    coverage = searched / total
    exhaustion = estimate_exhaustion_hours(remaining, rate)
    probability_24h = uniform_success_probability(remaining, rate, horizon_seconds)
    return {
        "keyspace_total": str(total),
        "keyspace_searched": str(searched),
        "keyspace_remaining": str(remaining),
        "coverage_pct": round(coverage * 100.0, 8),
        "active_workers": max(0, int(active_workers)),
        "attempts_per_second": round(rate, 6),
        "exhaustion_hours": None if exhaustion is None else round(exhaustion, 6),
        "probability_observed": round(coverage, 12),
        "probability_24h": round(probability_24h, 12),
        "expected_collision_candidates": None,
        "difficulty_category": classify_difficulty(exhaustion),
        "probability_model": probability_model,
        "reward_btc": max(0.0, float(reward_btc)),
        "measured_at": measured_at or datetime.now(timezone.utc).isoformat(),
    }

def expected_value_score(reward_btc: float, probability: float,
                         estimated_hours: float | None, *, reliability: float = 1.0) -> float:
    reward = max(0.0, float(reward_btc))
    probability = min(1.0, max(0.0, float(probability)))
    reliability = min(1.0, max(0.0, float(reliability)))
    if estimated_hours is None or estimated_hours <= 0:
        return 0.0
    return round((reward * probability / float(estimated_hours)) * reliability, 12)

def rank_key(metrics: dict[str, Any]) -> tuple:
    remaining = int(metrics.get("keyspace_remaining", 2**256))
    probability = float(metrics.get("probability_24h", 0.0))
    reward = float(metrics.get("reward_btc", 0.0))
    return (remaining, -probability, -reward)

def summarize_target(record: dict[str, Any]) -> dict[str, Any]:
    metrics = dict(record.get("search_metrics") or {})
    return {
        "id": record.get("id"),
        "title": record.get("title"),
        "reward_btc": float(record.get("reward_btc") or 0.0),
        "difficulty_category": metrics.get("difficulty_category", "UNRATED"),
        "keyspace_remaining": metrics.get("keyspace_remaining"),
        "coverage_pct": metrics.get("coverage_pct"),
        "attempts_per_second": metrics.get("attempts_per_second", 0),
        "probability_24h": metrics.get("probability_24h"),
        "exhaustion_hours": metrics.get("exhaustion_hours"),
        "expected_value_score": expected_value_score(
            float(record.get("reward_btc") or 0.0),
            float(metrics.get("probability_24h") or 0.0),
            metrics.get("exhaustion_hours"),
        ),
    }
