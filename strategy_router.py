"""Strategy router for public challenge analytics.

This module selects RUN / PAUSE / RESEARCH based on verified public metrics.
It never allocates private-key candidates and never launches a key-searcher.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from expected_value import expected_value_score


@dataclass(frozen=True)
class StrategyDecision:
    action: str
    reason: str
    score: float
    confidence: float
    signals: dict[str, Any]


def choose_strategy(record: dict[str, Any], *, electricity_btc_per_hour: float = 0.0,
                    min_probability_24h: float = 0.000001,
                    min_score: float = 0.0) -> StrategyDecision:
    m = dict(record.get("search_metrics") or {})
    reward = max(0.0, float(record.get("reward_btc") or 0.0))
    probability = max(0.0, min(1.0, float(m.get("probability_24h") or 0.0)))
    hours = m.get("exhaustion_hours")
    hours = None if hours is None else float(hours)
    reliability = max(0.0, min(1.0, float(m.get("reliability") or 1.0)))
    score = expected_value_score(reward, probability, hours, reliability=reliability)
    net_score = score - max(0.0, float(electricity_btc_per_hour))

    execution_mode = str((record.get("verification") or {}).get("execution_mode") or "RESEARCH").upper()
    adapter_ok = bool((record.get("verification") or {}).get("adapter_runnable"))
    if execution_mode == "RESEARCH" or not adapter_ok:
        return StrategyDecision("RESEARCH", "No independently audited runnable adapter.", score, reliability,
                                {"net_score": net_score, "execution_mode": execution_mode})
    if probability < min_probability_24h:
        return StrategyDecision("PAUSE", "Measured 24h probability is below threshold.", score, reliability,
                                {"net_score": net_score, "probability_24h": probability})
    if net_score <= min_score:
        return StrategyDecision("PAUSE", "Expected-value score does not clear cost threshold.", score, reliability,
                                {"net_score": net_score})
    return StrategyDecision("RUN", "Verified adapter and positive measured expected value.", score, reliability,
                            {"net_score": net_score, "probability_24h": probability})


def rank_targets(records: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
    ranked = []
    for record in records:
        decision = choose_strategy(record, **kwargs)
        ranked.append({**record, "strategy": {
            "action": decision.action,
            "reason": decision.reason,
            "score": decision.score,
            "confidence": decision.confidence,
            "signals": decision.signals,
        }})
    order = {"RUN": 0, "PAUSE": 1, "RESEARCH": 2}
    return sorted(ranked, key=lambda r: (
        order.get(r["strategy"]["action"], 9),
        -float(r["strategy"]["score"]),
        -float((r.get("search_metrics") or {}).get("probability_24h") or 0),
    ))
