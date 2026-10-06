# Satoshi Hunt Challenge Adapter SDK

A challenge adapter verifies a candidate only against an explicitly public reward challenge.

## Contract

Implement `ChallengeAdapter` from `verifier.py`:

- `challenge_type`: stable identifier.
- `verify(record, candidate)`: returns a boolean.
- The adapter must use only published challenge rules/material.
- Never read private keys, seed phrases, wallet credentials, hidden challenge data, or arbitrary filesystem secrets.
- Never broadcast transactions.
- Return `False` on malformed or incomplete records.

## Eligibility

A challenge must be:

1. `OPEN + FUNDED`
2. `public-reward-challenge`
3. backed by complete provenance
4. backed by complete verification metadata
5. registered server-side

## Reference adapter

`HashCommitmentAdapter` is included as a safe reference. It compares a worker-supplied candidate hash with an expected public commitment.

## Production checklist

Before registering a real adapter:

- independently reproduce the published verification rule;
- test valid, invalid, malformed and replayed candidates;
- confirm reward/funding provenance;
- add deterministic tests;
- add an audit event for verification;
- review the adapter for secret/private-key access;
- stage it before any real reward.
