# Automatic Real Public Challenge Rotation

Satoshi Hunt must not keep serving a challenge after somebody outside Satoshi Hunt has already solved it.

## State machine

OPEN + FUNDED -> EXTERNAL_SOLVED -> retired
                         |
                         v
                 select next eligible challenge

A challenge enters EXTERNAL_SOLVED only when an authoritative source provides verifiable evidence such as a confirmed payout/spending transaction or an independently reproducible published solution.

Social posts, screenshots, claims, or a third-party solved label alone are not enough.

## Rotation policy

1. Poll configured public sources.
2. Re-check the challenge's own authoritative evidence.
3. If solved externally, stop assigning new work immediately.
4. Record evidence URL, evidence ID, and timestamp.
5. Mark the challenge EXTERNAL_SOLVED.
6. Select the highest-funded eligible challenge from the verified pool.
7. Never activate a candidate whose live funding/provenance/verifier checks have not passed.
8. Preserve the retired challenge and evidence in history.
9. Rotation never authorizes or signs a payout.
