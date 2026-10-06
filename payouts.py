"""Non-custodial payout rail contract.

Satoshi Hunt queues a payout and records the external transaction reference after
an operator or external payout processor has actually broadcast the transaction.
No private keys or signing credentials are handled here.
"""
import re

TXID_RE = re.compile(r"^[0-9a-fA-F]{64}$")

def validate_external_txid(txid: str) -> bool:
    return bool(TXID_RE.fullmatch(str(txid).strip()))

def payout_contract():
    return {
        "custody": "none",
        "signing": "external",
        "flow": ["QUEUED", "PROCESSING", "PAID"],
        "requires_external_txid": True,
    }
