# Satoshi Hunt Deployment Guide

## Local staging

1. Copy `.env.example` to `.env` and replace every placeholder secret.
2. Start PostgreSQL and Redis with `docker compose -f docker-compose.staging.yml up -d db redis`.
3. Initialize the database with `docker compose -f docker-compose.staging.yml run --rm api python tools/init_db.py`.
4. Start the API with `docker compose -f docker-compose.staging.yml up -d api`.
5. Check `/health` and `/ready`.
6. Run `python production_check.py` with staging variables.
7. Run `python tools/staging_smoke.py`.
8. Run `pytest -q`.

## Production prerequisites

A real deployment still requires a managed PostgreSQL database, shared Redis, HTTPS/domain, email provider, secret manager, monitoring, backups, and operator credentials. Never copy the staging passwords into production.

## Database deployment

Apply `backend/schema.sql`, then every `backend/migrations/*.sql` in lexical order. Take a provider snapshot before migration. Prefer the provider's managed migration/backup mechanism for production.

## API

Run the container behind an HTTPS reverse proxy or managed ingress. Set an exact `FRONTEND_ORIGIN` and strong secrets. Do not expose PostgreSQL or Redis publicly.

## Rollout sequence

1. Backup/snapshot.
2. Apply schema/migrations.
3. Run production preflight.
4. Start API with one instance.
5. Check `/health`, `/ready`, `/network`, `/network/economics`.
6. Run smoke tests against staging first.
7. Enable additional API instances only after shared Redis and concurrency checks pass.
8. Keep real challenge allocation closed until a real challenge passes independent provenance/funding/verifier review.
9. Enable beta cohort.
10. Monitor before expanding traffic.
