# Phase 36 — Closed Beta

## Objective
Operate a deliberately limited beta without weakening Phase 35 safety gates.

## Beta rules
1. Beta access does not make a research challenge runnable.
2. Work is admitted only for explicitly runnable challenges.
3. Funding alone never implies runnable status.
4. Worker and account status must be active.
5. Beta capacity is bounded and fail-closed.
6. Reward settlement remains REVIEW until authorized approval.
7. Payout remains external and non-custodial.
8. Private-key, seed-phrase, and generic unbounded brute-force workloads remain forbidden.

## Entry gates
- Backend CI green.
- Staging E2E green.
- Production deployment healthy.
- Production smoke green for the current commit.
- Redis/rate-limit abuse test recorded.
- JWT/session and CORS/CSP deployed review recorded.
- Production secret rotation drill recorded.
- Independent security review recorded.
- At least one real bounded challenge passes challenge_qualification.

## Telemetry
Track active workers, assignments, rejection rate, coverage, throughput,
claims entering REVIEW, approved credits, withdrawals, 4xx/5xx responses,
rate-limit responses, and challenge pauses/stops.

## Rollback
If a runnable challenge shows verifier, economic, or abnormal error behavior:
pause the challenge, stop new assignments, preserve audit evidence, and
investigate before resuming.

Phase 36 does not replace the external security review or real runnable
challenge qualification gate.
