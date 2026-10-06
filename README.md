# Satoshi Hunt — Hybrid Puzzle Intelligence

Lightweight website + local CPU worker for publicly published reward puzzles.

## Current phase
- Normalized puzzle registry in `puzzles.json`
- Status/eligibility guards in `verifier.py`
- Registry audit in `audit.py`
- Local CPU queue guard in `worker.py`
- Dashboard filters for funded/open/solved/empty states

Only **OPEN + FUNDED** records are eligible for the local solver queue.

A zero balance alone is not proof that a puzzle was solved.

## Run worker
```bash
pip install -r requirements.txt
python worker.py
```

## Mobile worker

Android/Termux and lightweight Linux devices can use the battery-friendly API worker:

```bash
python mobile_worker.py
```

See MOBILE_WORKER.md for HTTPS configuration, Worker-token setup, five-device beta guidance, adaptive polling, and the explicit public-challenge safety boundary.


## Audit
```bash
python audit.py
```

## Next production layer
Connect a verified public challenge registry, read-only blockchain/indexer balance checks, deterministic challenge-specific verifiers, authenticated worker jobs, rate limits, audit logs, and explicit-permission submission adapters.

This project is not an ordinary Bitcoin wallet/private-key cracker. It is scoped to public challenges that explicitly publish a reward and permit solving.


## Job protocol
`protocol.py` creates bounded local jobs with CPU/time/candidate limits and a unique job ID. Candidate results are hashed for auditability. Public challenge claims can be verified automatically by a registered server-side adapter. Verified rewards are credited to the non-custodial reward ledger; actual BTC transfer remains outside the application.

## Registry integrity
Run `python audit.py` before loading a registry. The audit rejects duplicate IDs, contradictory funded/empty states, and balances larger than recorded rewards.

## Account, worker and reward model
- Each user account uses email login and registers a BTC payout address.
- One account may attach multiple opt-in worker devices.
- Work attribution is account + device + job based.
- A global work ledger must deduplicate previously tested candidates so failed work is not reassigned.
- The platform success fee is 15% of a verified reward; the worker account receives the remaining 85%.
- The platform fee is accounted separately from user rewards.
- A server-verified winning claim can be auto-credited to the worker account at 85%; if a payout address is already configured, a non-custodial withdrawal request is queued automatically.
- Satoshi Hunt never stores private keys or signs/broadcasts Bitcoin transactions; queued withdrawals require an external payout rail/operator to execute the actual BTC transfer.
- Community distribution is **owner-only and manual**: when the owner elects to allocate part of the owner's own 15% pool, eligible accounts receive shares based on verified worker-hours. Other users' 15% fees are never included in this pool.
- Reward settlement remains reviewable/auditable; private keys are never collected or stored.

## Production preflight

Before enabling a production deployment, run:

```bash
SATOSHI_HUNT_ENV=production python production_check.py
```

The check is side-effect free. It requires a configured PostgreSQL URL, strong JWT and challenge-ingestion secrets, an owner identity, a shared Redis rate-limit store, an explicit HTTPS frontend origin, and bounded worker allocation settings. It never handles private keys or sends Bitcoin.


## Deployment

- `DEPLOYMENT.md` documents local staging and production rollout.
- `Dockerfile` builds the API container.
- `docker-compose.staging.yml` provides PostgreSQL + Redis + API for local staging.
- `.env.example` lists required configuration without real secrets.
- `tools/init_db.py` applies schema and migrations in order.
- `tools/backup_db.sh` and `tools/restore_db.sh` provide PostgreSQL backup/restore helpers.
- `tools/staging_smoke.py` validates the verifier and reward-accounting contract without external side effects.

Production still requires real managed infrastructure, secrets, monitoring, backups, a real public challenge adapter, and external security review.


### Account and payout flow
- Accounts can use email + password authentication; passwords are stored only as salted PBKDF2-HMAC-SHA256 hashes.
- Users save a Bitcoin mainnet payout address on the account. Satoshi Hunt validates Base58Check P2PKH/P2SH and Bech32/Bech32m SegWit address formats before saving.
- A verified public-challenge solution credits the worker share (85%) to the solving account. If a payout address is already saved, the worker share is automatically reserved into a non-custodial withdrawal queue.
- The platform fee remains 15% and is recorded separately in the reward ledger.
- Satoshi Hunt does not hold private keys, seed phrases, or signing material. A queued withdrawal still requires an external payout processor/operator to perform the actual BTC transfer and record its external reference.
