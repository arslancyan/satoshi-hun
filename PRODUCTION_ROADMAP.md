# Satoshi Hunt — Production Roadmap

Satoshi Hunt is a coordination, verification, contribution-accounting, and audit layer for explicitly public reward challenges.

## 1. Assignment integrity
Implemented: claims are bound to an assignment ID; worker ID must match the assignment; account ownership is checked server-side; active assignment uniqueness is enforced by database index.

## 2. Worker reliability and expiry
Implemented: heartbeat timestamps; configurable assignment timeout; stale ASSIGNED/RUNNING work is marked EXPIRED; expired jobs return to QUEUED; stale-work index added.

## 3. Challenge adapters
Implemented: ChallengeAdapter contract; adapter registry; verifier result contract; no adapter means no verified solution.

## 4. Tests and race protection
Implemented: registry eligibility tests; canonical fingerprint tests; provenance/verification gating; database locking and unique active-assignment constraint.
Production expansion: PostgreSQL integration tests, concurrent assignment tests, replay/idempotency tests.

## 5. Public audit
Implemented: /audit/job/{job_id}; account contribution audit; verified/rejected claim counts; contribution seconds.

## 6. Worker reputation
Implemented: reliability score based on verified vs rejected claims; worker-hour accounting; worker activity timestamps.

## 7. Reward ledger
Implemented in schema: reward events; REVIEW -> APPROVED -> SETTLED -> VOID. 85/15 accounting can be represented without custody.
Important: no automatic Bitcoin transfer exists; no private keys are stored; settlement must remain authorized and auditable.

## 8. Community pool
Implemented in schema: manual-review community allocations; source reward event linkage; approval/distribution states. Owner-controlled allocations only; other users' platform fees are not automatically redirected to the pool.

## 9. Network dashboard
Frontend already exposes worker/network concepts. Production requirement: replace demo telemetry with backend-derived counts and never fabricate worker capacity.

## 10. Distributed backend
Current rate limiter is intentionally in-memory. Production requirement: use a shared rate-limit store or gateway; deploy PostgreSQL/Neon with TLS; configure HTTPS and exact frontend origin; rotate secrets and keep them server-side.

## 11. Production security audit
Required before real rewards: secret scanning; JWT/session hardening; replay protection; idempotency; concurrency tests; CORS/CSP review; database migration review; abuse/rate-limit testing; challenge provenance review.

## 12. Challenge onboarding and launch
Registry contract is defined in challenge-registry.schema.json.
A challenge becomes eligible only after: public source identified; reward/funding checked; published rules captured; verifier adapter exists; provenance and verification metadata fingerprinted; registry audit passes; challenge published as OPEN + FUNDED.

## Safety boundary
Satoshi Hunt does not request or store private keys or seed phrases, access wallets on behalf of users, perform covert/background computation, crack ordinary Bitcoin private keys, access private/non-public challenges, or automatically sign/send Bitcoin transactions. All computation must be opt-in and scoped to explicitly public reward challenges.
