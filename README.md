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
