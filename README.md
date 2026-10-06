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

## Audit
```bash
python audit.py
```

## Next production layer
Connect a verified public challenge registry, read-only blockchain/indexer balance checks, deterministic challenge-specific verifiers, authenticated worker jobs, rate limits, audit logs, and explicit-permission submission adapters.

This project is not an ordinary Bitcoin wallet/private-key cracker. It is scoped to public challenges that explicitly publish a reward and permit solving.


## Job protocol
`protocol.py` creates bounded local jobs with CPU/time/candidate limits and a unique job ID. Candidate results are hashed for auditability. No automatic fund transfer or claim is implemented.

## Registry integrity
Run `python audit.py` before loading a registry. The audit rejects duplicate IDs, contradictory funded/empty states, and balances larger than recorded rewards.

## Account, worker and reward model
- Each user account uses email login and registers a BTC payout address.
- One account may attach multiple opt-in worker devices.
- Work attribution is account + device + job based.
- A global work ledger must deduplicate previously tested candidates so failed work is not reassigned.
- The platform success fee is 15% of a verified reward; the worker account receives the remaining 85%.
- The platform fee is accounted separately from user rewards.
- Community distribution is **owner-only and manual**: when the owner elects to allocate part of the owner's own 15% pool, eligible accounts receive shares based on verified worker-hours. Other users' 15% fees are never included in this pool.
- Reward settlement remains reviewable/auditable; private keys are never collected or stored.
