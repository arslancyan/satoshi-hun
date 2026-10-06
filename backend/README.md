# Satoshi Hunt backend

Non-custodial API foundation for account, worker, job attribution and audit metadata.

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

## Security boundary

- Never store private keys, seed phrases, signing secrets, or wallet credentials.
- BTC payout addresses are treated as public destination metadata.
- Authentication uses short-lived signed sessions.
- Email delivery is intentionally not bundled; production deployment should connect an email provider for magic-link delivery.
- Reward records are accounting metadata and remain in REVIEW until an authorized operator approves settlement.
- No automatic Bitcoin transfer is implemented.

## API

- `GET /health`
- `POST /auth/request-link`
- `POST /auth/verify`
- `GET /me`
- `POST /workers`
- `GET /workers`
- `POST /jobs`
- `POST /jobs/{job_id}/claims`
- `GET /audit/account`

The API only creates jobs for the `public-reward-challenge` scope and deduplicates candidate hashes per job.
