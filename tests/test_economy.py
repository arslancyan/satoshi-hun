from decimal import Decimal

from economy import split_reward, validate_reward_event


def test_reward_split():
    result = split_reward("1")
    assert result["worker_share"] == Decimal("0.85000000")
    assert result["platform_fee"] == Decimal("0.15000000")
    assert validate_reward_event({
        "gross_reward_btc": result["gross"],
        "worker_share_btc": result["worker_share"],
        "platform_fee_btc": result["platform_fee"],
    })


def test_reward_split_rounds_down_without_overpaying():
    result = split_reward("0.00000003")
    assert result["worker_share"] + result["platform_fee"] == Decimal("0.00000003")
