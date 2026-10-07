# Satoshi Hunt — Challenge Metrics

Satoshi Hunt now treats challenge difficulty as measured telemetry rather than
a static QUICK / HARD / EXTREME label.

## Metrics

Each live challenge may publish keyspace_total, keyspace_searched,
keyspace_remaining, coverage_pct, active_workers, attempts_per_second,
exhaustion_hours, probability_24h, difficulty_category, probability_model,
and measured_at.

The marketplace can sort by lowest remaining work, highest 24-hour
probability, or highest verified reward.

## Important distinction

probability_24h is a statistical estimate, not a promise that a challenge will
be solved within 24 hours. For address/keyspace puzzles, the uniform model is
only a mathematical benchmark.

The ranking layer is deliberately separated from solver execution. A public
challenge must not become executable merely because metrics exist.

## #71

Public references currently describe #71 as an address-only puzzle with a
2^70-candidate range. Satoshi Hunt should display that as an EXTREME research
target and keep execution gated behind an independently audited adapter.
