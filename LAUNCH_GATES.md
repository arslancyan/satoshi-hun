# Satoshi Hunt Launch Gates

## Engineering
- [x] Protocol primitives
- [x] Worker lifecycle
- [x] Idempotency and replay protection
- [x] Economic allocation guard
- [x] Reward accounting
- [x] Audit ledger
- [x] Challenge verifier contract
- [x] Production configuration preflight

## Automated verification
- [x] Python compilation in CI
- [x] Unit/regression tests
- [x] PostgreSQL schema and migrations in CI
- [x] Challenge registry JSON validation
- [x] Staging happy-path contract tests
- [x] Concurrency contract tests
- [ ] GitHub Actions result confirmed green on main

## Staging infrastructure
- [ ] PostgreSQL staging
- [ ] Shared Redis staging
- [ ] HTTPS API
- [ ] Email provider
- [ ] End-to-end lifecycle execution
- [ ] Concurrent multi-process test
- [ ] Backup/restore drill

## Real challenge
- [ ] Independently verified public challenge source
- [ ] Funding independently checked
- [ ] Challenge-specific verifier reviewed
- [ ] Provenance fingerprint recorded
- [ ] Challenge published as OPEN + FUNDED only after verification

## Security
- [ ] External security review
- [ ] High/critical dependency/static findings cleared
- [ ] JWT/session review
- [ ] CORS/CSP review
- [ ] Rate-limit abuse testing
- [ ] Secret rotation drill

## Beta and public launch
- [ ] Small opt-in worker cohort
- [ ] Monitoring and incident response tested
- [ ] Manual reward review tested
- [ ] Production backups verified
- [ ] Owner settlement procedure documented
- [ ] Safety boundary published
