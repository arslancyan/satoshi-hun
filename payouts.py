"""Non-custodial payout rail contract for Satoshi Hunt.

This module never signs or broadcasts Bitcoin. It validates the accounting
boundary between a verified reward and an externally executed payout.
"""

from decimal import Decimal
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
        "requires_approved_settlement": True,
    }


def build_payout_request(reward_event, destination_wallet):
    if reward_event.get("settlement_status") != "APPROVED":
        raise ValueError("payout requires an APPROVED settlement")
    amount = Decimal(str(reward_event.get("worker_share_btc", "0")))
    if amount <= 0:
        raise ValueError("payout amount must be positive")
    wallet = str(destination_wallet).strip()
    if not wallet:
        raise ValueError("destination wallet is required")
    return {
        "status": "QUEUED",
        "destination_wallet": wallet,
        "amount_btc": amount,
        "requires_external_txid": True,
    }


def finalize_external_payout(request, txid):
    if request.get("status") != "PROCESSING":
        raise ValueError("payout must be PROCESSING before finalization")
    if not validate_external_txid(txid):
        raise ValueError("invalid external Bitcoin transaction id")
    return {
        **request,
        "status": "PAID",
        "external_txid": str(txid).strip().lower(),
    }
