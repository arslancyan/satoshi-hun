"""Adaptive public-challenge rotation.

Ranks already-verified public challenges from current telemetry. This module
does not solve puzzles or derive credentials; it only decides which verified
records deserve queue/display priority.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from strategy_router import choose_strategy


def _metric(record: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = (record.get("search_metrics") or {}).get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def freshness_score(record: dict[str, Any], now: datetime | None = None) -> float:
    stamp = _metric(record, "freshness_seconds", -1)
    if stamp >= 0:
        return max(0.0, min(1.0, 1.0 - stamp / 86400.0))
    raw = (record.get("search_metrics") or {}).get("measured_at")
    if not raw:
        raw = record.get("live_checked_at")
    if not raw:
        return 0.0
    try:
        measured = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if measured.tzinfo is None:
            measured = measured.replace(tzinfo=timezone.utc)
        age = max(0.0, (now or datetime.now(timezone.utc) - measured).total_seconds())
        return max(0.0, min(1.0, 1.0 - age / 86400.0))
    except ValueError:
        return 0.0


def opportunity_score(record: dict[str, Any]) -> float:
    metrics = record.get("search_metrics") or {}
    probability = max(0.0, min(1.0, _metric(record, "probability_24h")))
    reward = max(0.0, float(record.get("balance_btc") or record.get("reward_btc") or 0.0))
    reliability = max(0.0, min(1.0, _metric(record, "reliability", 1.0)))
    funding = 1.0 if bool((record.get("verification") or {}).get("funding_match")) else 0.0
    workers = max(0.0, _metric(record, "active_workers"))
    competition = 1.0 / (1.0 + workers)
    freshness = freshness_score(record)

    # Probability is the dominant signal. Reward is capped so a huge,
    # low-probability bounty cannot crowd out a measurable opportunity.
    reward_signal = min(1.0, reward / 10.0)
    score = (
        probability * 0.55
        + reward_signal * 0.08
        + reliability * 0.12
        + funding * 0.10
        + freshness * 0.08
        + competition * 0.07
    )
    return round(score, 12)


def rank_challenges(records: list[dict[str, Any]], *, limit: int = 30,
                    queue_limit: int = 30) -> dict[str, list[dict[str, Any]]]:
    ranked = []
    for record in records:
        decision = choose_strategy(record)
        item = {
            **record,
            "opportunity_score": opportunity_score(record),
            "strategy": {
                "action": decision.action,
                "reason": decision.reason,
                "score": decision.score,
                "confidence": decision.confidence,
                "signals": decision.signals,
            },
        }
        ranked.append(item)

    ranked.sort(
        key=lambda x: (
            {"RUN": 0, "PAUSE": 1, "RESEARCH": 2}.get(
                x["strategy"]["action"], 9
            ),
            -float(x["opportunity_score"]),
            -float(x["strategy"]["score"]),
            str(x.get("id", "")),
        )
    )

    runnable = [
        x for x in ranked
        if x["strategy"]["action"] == "RUN"
        and (x.get("verification") or {}).get("adapter_runnable") is True
        and (x.get("verification") or {}).get("execution_mode") == "COMPUTE"
        and x.get("status") == "OPEN + FUNDED"
        and float(x.get("balance_btc") or 0) > 0
    ]

    return {
        "ranked": ranked[:max(0, int(limit))],
        "queue": runnable[:max(0, int(queue_limit))],
    }
