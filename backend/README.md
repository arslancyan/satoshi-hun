# Satoshi Hunt backend

Non-custodial API foundation for account, worker, job assignment and audit metadata.

## Run

1. Copy `.env.example` to your local environment.
2. Apply `schema.sql` to PostgreSQL.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Start:

```bash
uvicorn api:app --host 127.0.0.1 --port 8000
```

## Worker API mode

The opt-in worker can poll assignments and report server-side heartbeats.

Set:

```bash
export SATOSHI_HUNT_API="https://your-api.example"
export SATOSHI_HUNT_TOKEN="YOUR_WORKER_TOKEN"
export SATOSHI_HUNT_WORKER_ID="YOUR_REGISTERED_WORKER_UUID"
python worker.py
```

The worker:
- accepts only assignments already attached to its registered worker;
- starts and heartbeats assignments;
- submits a non-solving demo candidate marker;
- completes the assignment so server timestamps become verified worker-hours;
- never receives or stores private keys, seed phrases, or wallet credentials.

A real challenge adapter must be added separately for each public reward challenge and must use that challenge's published verification rules. A registry entry is not solver-eligible until trusted provenance and verification metadata are present.

## Security boundary

- Never store private keys, seed phrases, signing secrets, or wallet credentials.
- BTC payout addresses are treated as public destination metadata.
- Authentication uses short-lived signed sessions.
- Email delivery is intentionally not bundled; production deployment should connect an email provider for magic-link delivery.
- Reward records are accounting metadata and remain in REVIEW until an authorized operator approves settlement.
- No automatic Bitcoin transfer is implemented.
- Redis-backed rate limiting is supported; production should use a shared/distributed limiter and fail closed at the gateway if Redis is unavailable.
- Authenticated account mutations accept `Idempotency-Key`; replays return the original response and mismatched reuse returns `409`.
- Production migrations must be applied in order, including `migrations/005_idempotency.sql`.
- The challenge ingestion path validates the registry entry before creating a job, so `jobs.puzzle_id` is guarded by application-level provenance validation.

## API

- `GET /health`
- `POST /auth/request-link`
- `POST /auth/verify`
- `GET /me`
- `POST /workers`
- `GET /workers`
- `POST /workers/{worker_id}/heartbeat`
- `GET /workers/{worker_id}/assignments`
- `POST /internal/challenges` (server-to-server ingestion; requires `X-Challenge-Ingestion-Key`)
- `POST /jobs` (intentionally blocked for direct user creation)
- `GET /jobs`
- `GET /jobs/{job_id}`
- `POST /jobs/{job_id}/assign`
- `POST /jobs/{job_id}/claims`
- `POST /assignments/{assignment_id}/start`
- `POST /assignments/{assignment_id}/heartbeat`
- `POST /assignments/{assignment_id}/complete`
- `GET /audit/account`

Job state is intentionally separate from solution verification:
`QUEUED → RUNNING → COMPLETED`, while a challenge-specific verified result moves a job to `VERIFIED`.

The API only creates jobs for the `public-reward-challenge` scope. Challenge ingestion requires complete provenance/verification metadata and is idempotent for active jobs. Candidate hashes are deduplicated per job.
