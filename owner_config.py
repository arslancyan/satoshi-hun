"""Immutable Satoshi Hunt owner platform-fee destination.

This address is not user-configurable. The database migration independently
enforces the same value for every PLATFORM_FEE ledger entry.
"""

OWNER_PLATFORM_FEE_BTC_ADDRESS = "bc1psfusgszcfvtw243uu9hq0fvdhta7s2lc8ufmr2n0f9eaw6qezxusa4pa8m"
PLATFORM_FEE_SHARE = "0.15"
WORKER_SHARE = "0.85"
