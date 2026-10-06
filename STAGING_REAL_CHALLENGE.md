# Real public challenge staging

Satoshi Hunt is wired to one live, public, funded challenge family:

- Peter Todd Hash Collision Bounties
- Four live Bitcoin P2SH escrows
- Registry snapshot: 0.59364885 BTC across the four escrows
- Verification input: two distinct byte strings plus one published hash function
- No private keys, seed phrases, or wallet credentials are accepted

Public provenance: https://bitcointalk.org/index.php?topic=293382.0

This is a cryptanalysis research bounty, not routine profitable brute-force work.
The worker policy therefore forbids treating it as ordinary compute.

## Acceptance flow

1. Load the challenge registry record.
2. Confirm OPEN + FUNDED plus complete provenance and verification metadata.
3. Register the challenge adapter.
4. Run negative-control, malformed, same-message and oversized candidates.
5. A genuine collision is verified locally against the named hash.
6. Create the reward event in REVIEW.
7. Owner approval moves settlement to APPROVED.
8. Create a payout request for the user's saved wallet address.
9. An external payout processor signs and broadcasts.
10. Only a valid external transaction id moves the request to PAID.
11. Verify audit-chain integrity and idempotency.

Staging never broadcasts a transaction and never stores signing credentials.
