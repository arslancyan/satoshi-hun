# Satoshi Hunt Operations Runbook

## Health checks

1. Run production preflight before deployment.
2. Check /health and /ready.
3. Check /network and /network/economics.
4. Confirm shared Redis is reachable from every API process.
5. Confirm database connection and migration version.

## Allocation anomaly

Stop new allocation, preserve assignments/claims/reward events/audit records, inspect economics and audit data, and reopen only after the cause is understood and preflight passes.

## Worker credential compromise

Revoke the affected worker token, preserve audit records, rotate the token, and review associated assignments and claims.

## Redis failure

Treat shared rate limiting as degraded. Keep production allocation closed if shared Redis is required by policy. Restore Redis, rerun preflight and concurrency checks, then reopen.

## Database failure

Stop new allocation. Preserve the database snapshot. Restore only through the approved procedure. Verify migrations, audit-chain integrity, reward-event counts, and staging smoke tests before reopening.

## Backup and restore drill

1. Take a managed PostgreSQL backup/snapshot.
2. Restore into an isolated database.
3. Verify schema and migration state.
4. Compare counts for accounts, workers, jobs, assignments, claims, worker-hours, reward events, and audit events.
5. Verify representative audit chains.
6. Run tools/staging_smoke.py.
7. Record restore duration and missing-data findings.

A restore is not successful if claims, worker-hours, reward events, or audit records disappear.

## Release gate

Production opening requires CI green, production preflight, staging acceptance, concurrency tests, backup/restore drill, independently reviewed real challenge adapter, external security review, active monitoring/alerting, and tested manual reward settlement.
