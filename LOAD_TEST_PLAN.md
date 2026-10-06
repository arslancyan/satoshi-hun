# Satoshi Hunt Load Test Plan

## Goals

- prove one active assignment per job under concurrency;
- prove duplicate candidate claims are rejected;
- measure API latency under worker polling;
- verify Redis rate limiting remains shared across instances;
- verify stale assignment recovery.

## Scenarios

### Assignment race
Create one queued job and concurrently attempt assignment from multiple workers. Expected: exactly one active assignment.

### Claim replay
Submit the same `candidate_hash` concurrently. Expected: one claim succeeds and subsequent inserts are duplicate/rejected.

### Worker polling
Simulate workers polling at the configured interval. Monitor database connection usage and API p95 latency.

### Expiry storm
Create many stale assignments and verify expiry processing returns jobs to QUEUED without duplicate active assignments.

## Beta target

Start with 10–25 workers in staging. Increase gradually only after database and Redis metrics remain healthy.
