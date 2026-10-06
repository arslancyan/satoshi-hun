"""Non-custodial reward accounting helpers.

These functions calculate ledger values only. They never sign, broadcast, or
custody Bitcoin.
"""
from decimal import Decimal, ROUND_DOWN

WORKER_SHARE = Decimal("0.85")
PLATFORM_SHARE = Decimal("0.15")
BTC_QUANT = Decimal("0.00000001")


def split_reward(gross_btc):
    gross = Decimal(str(gross_btc)).quantize(BTC_QUANT)
    if gross <= 0:
        raise ValueError("gross reward must be positive")
    worker = (gross * WORKER_SHARE).quantize(BTC_QUANT, rounding=ROUND_DOWN)
    fee = gross - worker
    return {"gross": gross, "worker_share": worker, "platform_fee": fee}


def validate_reward_event(event):
    gross = Decimal(str(event["gross_reward_btc"]))
    worker = Decimal(str(event["worker_share_btc"]))
    fee = Decimal(str(event["platform_fee_btc"]))
    return gross > 0 and worker >= 0 and fee >= 0 and worker + fee == gross
