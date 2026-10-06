# Satoshi Hunt Staging Runbook

## Required services

- PostgreSQL with TLS
- Redis for shared rate limiting
- Backend API over HTTPS
- GitHub Pages or equivalent frontend
- Email provider for magic links

## Required secrets

- DATABASE_URL
- JWT_SECRET
- CHALLENGE_INGESTION_KEY
- OWNER_EMAIL
- RATE_LIMIT_REDIS_URL

Never commit production values.

## Deployment order

1. Apply `backend/schema.sql` to a fresh staging database, or apply migrations 001–003 to an existing database.
2. Configure environment variables.
3. Start the API.
4. Verify `GET /health`.
5. Verify `GET /network`.
6. Register a staging account and worker.
7. Ingest only a test public-reward challenge with complete provenance.
8. Assign, start, heartbeat and complete a worker job.
9. Submit a TESTED claim.
10. Verify it through the registered adapter.
11. Confirm the reward event is REVIEW.
12. Approve, then settle it through the owner endpoint.
13. Verify the audit chain.
14. Confirm duplicate requests do not create duplicate reward events.
15. Run load/concurrency tests before beta.

## Incident response

- Revoke compromised worker tokens immediately.
- Disable challenge ingestion by removing `CHALLENGE_INGESTION_KEY`.
- Keep reward events in REVIEW during disputes.
- Never request or store a user's private key or seed phrase.
- Preserve audit events and database logs for investigation.

## Migration verification

After applying the schema and migrations, verify the migration set is reproducible on a fresh PostgreSQL database. CI applies backend/schema.sql followed by every backend/migrations/*.sql file in lexical order. Do not manually reorder migrations in staging.

For an existing database, take a backup/snapshot before migration. Apply one migration batch at a time and verify /ready plus the database connection before continuing.

## Rollback policy

Migrations are treated as forward-only unless a tested rollback migration exists. For a failed deployment:

1. Stop new worker allocation.
2. Keep existing assignments in their current state; do not delete contribution records.
3. Preserve audit and reward-ledger data.
4. Restore the database only through the approved staging/production restore procedure when required.
5. Re-run the preflight and schema checks before reopening allocation.

Never use a rollback procedure that can silently erase reward events, claims, worker-hours, or audit events.

## Staging acceptance checklist

- [ ] SATOSHI_HUNT_ENV=production python production_check.py passes against staging configuration.
- [ ] CI compile/tests pass.
- [ ] Fresh-database schema + migrations apply successfully.
- [ ] Shared Redis rate limiting works from more than one API process.
- [ ] Worker registration, heartbeat, rotation, revoke, and assignment lifecycle pass.
- [ ] Duplicate idempotent requests replay the original response without duplicate state changes.
- [ ] A test public challenge can be ingested only with complete provenance and verification metadata.
- [ ] Candidate verification requires a registered challenge adapter.
- [ ] Reward event remains REVIEW until owner approval.
- [ ] Audit chain verifies after the complete test flow.
- [ ] Allocation caps reject excess concurrent work.
