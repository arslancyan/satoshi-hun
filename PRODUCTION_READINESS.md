# Satoshi Hunt Production Readiness

## Completed in repository
- Public reward challenge scope only
- Challenge provenance + verification gating
- Assignment expiry and heartbeat
- Per-worker authentication tokens (hashed at rest)
- Worker-to-assignment authorization
- Candidate uniqueness per job
- Contribution-time accounting
- 85/15 non-custodial reward accounting
- Deterministic work-range allocator
- Tamper-evident audit-event ledger
- Dependency and static security checks in CI
- No private keys, seed phrases, wallet credentials, automatic signing, or automatic BTC broadcast

## Requires production infrastructure or operator credentials
- PostgreSQL/Neon production database and migration execution
- Managed Redis for shared rate limiting
- Production email provider for sign-in links
- Secret manager for JWT and database credentials
- TLS/domain configuration
- Monitoring, alerting, backups, restore drills (runbook added; execution still requires production infrastructure)
- External penetration test / security review
- Real public challenge adapter: Peter Todd hash-collision bounty verifier (research-breakthrough scope; not a routine profitable compute job) and authoritative public provenance record
- Non-custodial payout queue with owner processing state and mandatory external Bitcoin txid before PAID
- Manual reward settlement operations

## Local/staging hardening added
- End-to-end challenge → verifier → reward accounting contract tests
- Concurrency/unique-assignment contract tests
- Side-effect-free staging smoke script
- Operations, backup/restore, and incident-response runbook
- Explicit launch-gate checklist

## Launch gates
1. CI green on main.
2. Database migrations applied to a staging database.
3. Integration tests pass against staging PostgreSQL.
4. Redis rate limiting verified under concurrent load.
5. Worker token rotation/revocation tested.
6. Race tests prove one active assignment per job.
7. Audit chain verification tested.
8. Reward settlement transitions tested.
9. No high/critical dependency or static-analysis findings.
10. External security review completed.
11. At least one real public challenge has independently verified provenance, funding, and published verification rules. **Repository adapter/manifest is now present; live escrow must be rechecked immediately before enabling it for production.**
12. External payout processor is configured; only externally confirmed Bitcoin transaction IDs can move a withdrawal to PAID.
