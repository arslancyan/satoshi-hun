# Satoshi Hunt — Minimum-Cost Beta

This beta deployment keeps the existing FastAPI, verifier, protocol, anti-cheat, accounting, audit, and worker code. It adds a deployment path rather than replacing the backend.

## Target cost

**$0/month for a small controlled beta**, using free-tier infrastructure.

Recommended initial paid fallback: **$5–10/month** only when free-tier limitations begin affecting availability or testing.

## Free-tier topology

- Frontend: existing GitHub Pages site.
- API: Render Free Web Service using the existing Dockerfile.
- PostgreSQL: Neon Free PostgreSQL.
- Shared rate-limit store: Render Free Key Value (Valkey-compatible with redis-py).
- Transactional email: optional Resend Free.
- Worker compute: user's own opt-in device.
- Bitcoin payout: manual/owner-gated only.

Render explicitly describes Free web services as suitable for testing, hobby projects, and previews, not production. Free web services can spin down after inactivity and have a monthly instance-hour allowance. Free Key Value is in-memory and loses its data on restart, so it must not be used as the source of truth. The Satoshi Hunt database remains the source of truth.

## Required beta secrets

Configure these in Render as environment variables:

- DATABASE_URL — Neon PostgreSQL connection string.
- JWT_SECRET — random secret, at least 32 characters.
- CHALLENGE_INGESTION_KEY — random secret, at least 32 characters.
- OWNER_EMAIL — owner account email.
- FRONTEND_ORIGIN — exact deployed frontend origin.
- RATE_LIMIT_REDIS_URL — Render Key Value connection URL.

Never commit these values to Git.

## Beta safety limits

The included render.yaml deliberately starts below production allocation limits:

- MAX_ACTIVE_ASSIGNMENTS=10
- MAX_ACTIVE_ASSIGNMENTS_PER_JOB=1
- MAX_NETWORK_WORKER_HOURS_PER_DAY=100

These are beta allocation limits, not economic guarantees.

## What remains unchanged

The beta still uses:

- public-reward-challenge scope
- provenance and verification gates
- local-first worker computation
- worker tokens
- worker/account attribution
- idempotency
- assignment expiry/recovery
- checkpoint/resume
- duplicate claim protection
- server-bounded CPU accounting
- verifier adapters
- 85/15 reward accounting
- owner-gated reward settlement
- community allocation controls
- audit ledger
- reputation and anti-cheat scoring
- scheduler/economic capacity controls

## What beta must NOT enable

- private-key or seed-phrase handling
- unauthorized wallet solving
- covert/background compute
- automatic Bitcoin broadcasting
- automatic custody of user funds
- unfunded or unverified challenges
- claims that demo records are live rewards

## Beta launch sequence

1. Create Render account/workspace.
2. Create a free Key Value instance.
3. Create a Neon Free project and apply backend/schema.sql plus migrations.
4. Create the Render Web Service from render.yaml.
5. Add the required secrets.
6. Confirm /health, /ready, /network, and /network/economics.
7. Point the existing frontend API configuration at the Render API.
8. Run the staging smoke/contract tests.
9. Ingest one independently verified public reward challenge.
10. Invite a small number of testers.
11. Keep reward settlement manual and owner-gated.

## Important reliability boundary

This is a beta/preview architecture, not a production SLA architecture. Render Free services can sleep/restart and its Free Key Value store is not persistent. PostgreSQL and the append-only audit/reward records remain authoritative.

Upgrade only the component that becomes the bottleneck. Do not buy a VPS merely because the beta has started.
