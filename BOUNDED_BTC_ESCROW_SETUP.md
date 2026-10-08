# Satoshi Hunt Bounded BTC Escrow Setup

Satoshi Hunt now supports a permissionless bounded BTC challenge format using a native Bitcoin P2WSH escrow.

## How it works

Each challenge commits to:

- preimage: `<challenge_id>:<nonce>`
- SHA-256(preimage) must be below the published difficulty target
- witness script: `OP_SHA256 <digest> OP_EQUALVERIFY OP_TRUE`
- P2WSH escrow is spendable by anyone who finds the valid preimage
- Satoshi Hunt never stores a private key and never signs the payout

## Prepared public challenges

| Challenge | Difficulty | Max nonce | Reward | Escrow |
|---|---:|---:|---:|---|
| QUICK | 16 bits | 1,048,575 | 10,000 sats | bc1qq275r5a96zjh9seap6pha5tlea2mjnndy3adv4zylq2w3wgr6mnqzx7dyp |
| HARD | 20 bits | 4,194,303 | 20,000 sats | bc1q9ay6gzz9fypjjjnmasq0u24tzd7dur95a7fvj0ly8fryjzpldw4qpmyg7v |
| EXTREME | 24 bits | 16,777,215 | 50,000 sats | bc1qa8yh4ezhpjhhdg8z0whr2csr7ttpv0vqz3t9ptsaw6q4x72r6frsq6nlq3 |

Fund the exact reward amount to each escrow. The challenge-sync worker independently checks the on-chain balance before changing the challenge to OPEN + FUNDED.

## Promotion gates

A challenge is not runnable merely because its manifest exists. Production promotion requires:

1. exact escrow address is funded on-chain;
2. funding amount meets the published reward;
3. deterministic verifier and bounded solver pass adapter audit;
4. permissionless payout metadata is valid;
5. challenge registry audit passes;
6. the marketplace receives the challenge as runnable.

Until funding is observed, these three remain OPEN + UNFUNDED and cannot receive worker jobs.

## Known calibration solutions

The known vectors are only for verifier/adapter testing:

- QUICK: nonce 10,697
- HARD: nonce 584,976
- EXTREME: nonce 14,248,268

They are not payout claims and are not inserted into the production reward ledger.
