"""Adaptive ranking for public reward challenges.

This module is analytics-only and does not execute challenge work.
"""
from __future__ import annotations
from datetime import datetime, timezone
from math import exp
from typing import Any


def clamp(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def freshness_score(measured_at: str | None, half_life_hours: float = 12.0) -> float:
    if not measured_at:
        return 0.0
    try:
        stamp = datetime.fromisoformat(str(measured_at).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age = max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds() / 3600.0)
        return round(exp(-age / max(0.1, half_life_hours)), 6)
    except (TypeError, ValueError):
        return 0.0


def funding_confidence(advertised: float, verified: float, matched: bool, stale: bool) -> float:
    if stale or advertised <= 0:
        return 0.0
    ratio = min(1.0, max(0.0, verified / advertised))
    return round(ratio if matched else ratio * 0.25, 6)


def lead_signal(leads: list[Any] | None, certified: bool, mode: str) -> float:
    score = min(0.6, len(leads or []) * 0.12)
    score += 0.25 if certified else 0.0
    score += 0.15 if str(mode).upper() == "COMPUTE" else 0.0
    return round(clamp(score), 6)


def competition_score(workers: int, rate: float) -> float:
    worker_part = 1.0 / (1.0 + max(0, workers) / 10.0)
    rate_part = 1.0 / (1.0 + max(0.0, rate))
    return round(clamp(0.65 * worker_part + 0.35 * rate_part), 6)


def build_opportunity_metrics(record: dict[str, Any]) -> dict[str, Any]:
    verification = dict(record.get("verification") or {})
    metrics = dict(record.get("search_metrics") or {})
    reward = max(0.0, float(record.get("reward_btc") or 0.0))
    probability = clamp(float(metrics.get("probability_24h") or 0.0))
    reliability = clamp(float(metrics.get("reliability") or 1.0))
    funding = funding_confidence(
        float(verification.get("advertised_reward_btc") or reward),
        float(verification.get("verified_balance_btc") or record.get("balance_btc") or 0.0),
        bool(verification.get("funding_match")),
        bool(verification.get("verification_stale")),
    )
    freshness = freshness_score(metrics.get("measured_at") or verification.get("checked_at"))
    leads = lead_signal(
        verification.get("leads") or [],
        bool(verification.get("oracle_certified")),
        str(verification.get("execution_mode") or "RESEARCH"),
    )
    competition = competition_score(
        int(metrics.get("active_workers") or 0),
        float(metrics.get("attempts_per_second") or 0.0),
    )
    score = (
        probability * 0.40
        + min(1.0, reward) * 0.15
        + reliability * 0.15
        + funding * 0.12
        + freshness * 0.08
        + leads * 0.07
        + competition * 0.03
    )
    return {
        "opportunity_score": round(score, 8),
        "probability_24h": round(probability, 12),
        "reward_btc": round(reward, 8),
        "reliability": round(reliability, 6),
        "funding_confidence": funding,
        "freshness": freshness,
        "lead_signal": leads,
        "competition_score": competition,
        "scoring_version": "opportunity-v1",
    }


def rank_opportunities(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = []
    for record in records:
        opportunity = build_opportunity_metrics(record)
        ranked.append({**record, "opportunity": opportunity})
    return sorted(ranked, key=lambda r: (
        -float(r["opportunity"]["opportunity_score"]),
        -float(r["opportunity"]["probability_24h"]),
        -float(r["opportunity"]["reward_btc"]),
        str(r.get("id") or ""),
    ))
