# Phase 35 — Security & Economic Audit

## Scope

This repository audit covers the controls that can be verified without production
credentials, private keys, or an external security assessor.

## Findings

| Area | Result | Evidence / rule |
|---|---|---|
| Custody boundary | PASS | No private keys, seed phrases, signing credentials, or automatic BTC broadcast are part of the worker protocol |
| Reward settlement | PASS | Verified claims enter REVIEW; only authorized owner approval can create worker credit and withdrawal |
| Payout finality | PASS | Withdrawal cannot become PAID without an externally supplied 64-hex transaction id |
| Payout idempotency | PASS | Completion requires PROCESSING and rejects invalid/repeated finalization |
| Payout limits | PASS | Per-payout and daily payout caps are enforced |
| Assignment exclusivity | PASS | Active assignment cap plus database locking/race tests prevent duplicate active work |
| Candidate uniqueness | PASS | Candidate uniqueness is enforced per job |
| Work accounting | PASS | Contribution time and 85/15 reward accounting are persisted through the reward ledger |
| Challenge promotion | PASS | New fail-closed qualification gate requires provenance, funding, permissionless payout, deterministic verifier, bounded search, vectors, and audited adapter |
| Forbidden search scope | PASS | Private-key search, seed-phrase search, and generic unbounded brute force explicitly fail qualification |
| Public challenge state | PASS | Peter Todd, Aoi Nakamoto, Genesis, Corey, Keir and RushWallet research records remain non-runnable |
| External security review | BLOCKED | Requires an independent assessor; cannot be truthfully marked complete by repository tests |
| Production secret/infra review | BLOCKED | Requires live operator environment and secret manager |
| Real runnable public challenge | BLOCKED | No currently discovered public challenge has a bounded, independently audited compute domain |

## Economic invariants

1. A worker cannot withdraw a reward merely by submitting a candidate.
2. A verified claim does not immediately create spendable balance.
3. Owner approval is required before worker credit and withdrawal reservation.
4. The platform fee and worker share are ledgered together.
5. A withdrawal cannot be finalized without an external transaction id.
6. Payout caps prevent a single queue item or daily queue from exceeding configured limits.
7. Research/unbounded challenges cannot consume worker compute through the runnable queue.
8. A public funding record is not sufficient to make a challenge runnable.

## Remaining Phase 35 gates

- [ ] Run latest main CI/staging/production smoke and record green results.
- [ ] Run production secret rotation drill.
- [ ] Run Redis/rate-limit abuse test against staging.
- [ ] Complete JWT/session and CORS/CSP review in the deployed environment.
- [ ] Obtain independent external security review.
- [ ] Obtain one real bounded public challenge and pass the qualification contract.
