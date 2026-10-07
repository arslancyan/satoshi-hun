# Satoshi Hunt — No-Cost Next Phase

This phase is intentionally limited to work that can be completed before renting a VPS or enabling production infrastructure.

## Goal

Finish repository-side engineering, documentation, safety checks, and public-demo readiness without handling real funds or requiring a paid server.

## Work that can be completed now

### 1. Repository verification
- Keep main as the release branch.
- Confirm Python compilation and regression tests in GitHub Actions when Actions runs are available.
- Review dependency/static-analysis configuration.
- Keep production launch gates unchecked until staging evidence exists.

### 2. Public challenge safety
- Keep every solver-eligible record gated by:
  - OPEN + FUNDED
  - public-reward-challenge
  - complete provenance
  - complete verification metadata
  - registered challenge-specific adapter
- Do not add private-key, seed-phrase, wallet-credential, or hidden-challenge adapters.
- Do not add automatic Bitcoin signing or broadcasting.

### 3. Scheduler and worker hardening
- Keep one active assignment per job as the default economic safety rule.
- Keep network assignment and worker-hour caps configurable.
- Keep idempotency on account and worker mutation endpoints.
- Keep the Android/Termux mobile worker in safe transport mode by default, with explicit demo-only protocol activation.
- Continue contract tests for allocation races, replay, checkpoint/resume, and claim uniqueness.

### 4. Frontend/demo readiness
- Keep puzzle selection and local worker execution as the primary workflow.
- Make funding/eligibility state unambiguous without implying that demo records are live opportunities.
- Keep secondary audit, reputation, economics, and operator panels discoverable but less prominent.
- Preserve the local-first model: computation happens on the worker device.

### 5. Operations documentation
Keep deployment, backup/restore, incident response, and launch-gate documents synchronized with the implementation.

## Work that must wait for staging infrastructure

The following should not be marked complete from repository-only work:

1. PostgreSQL staging migration execution.
2. Shared Redis concurrency/rate-limit validation.
3. HTTPS API deployment.
4. Email provider integration.
5. Backup/restore drill against a real staging database.
6. Multi-process API race testing.
7. Real public challenge provenance/funding verification.
8. External security review.
9. Manual reward settlement rehearsal.
10. Beta worker cohort.

## When the VPS is eventually purchased

Use the existing staging deployment path:

1. Provision Ubuntu 24.04 VPS.
2. Install Docker Engine + Compose.
3. Clone the latest main.
4. Configure .env with staging-only secrets.
5. Start PostgreSQL and Redis.
6. Run db-init.
7. Start the API.
8. Check /health, /ready, /network, and /network/economics.
9. Run pytest -q.
10. Run the staging smoke test.
11. Execute the full lifecycle against a test public challenge.
12. Only after all evidence passes, review the production launch gates.

## Safety rule

Until independent staging and challenge verification are complete, Satoshi Hunt remains a development/staging system. Demo balances and challenge records must never be presented as guaranteed live rewards.


## Repository closure additions

- Live-source sync now uses the same challenge-discovery readiness decision as marketplace/execution.
- Research/verified challenges are prevented from entering the worker queue during normal sync and replacement rotation.
- Adapter readiness is persisted in challenge verification metadata for auditability.
- The current Peter Todd bounty family remains VERIFIED/RESEARCH until a bounded, independently audited collision solver exists.
- The bounded-leading-zero adapter remains a test/reference capability and does not create a live funded opportunity by itself.
