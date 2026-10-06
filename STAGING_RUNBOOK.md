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
