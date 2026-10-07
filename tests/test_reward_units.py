from decimal import Decimal
from pathlib import Path
import ast


API_SOURCE = Path("backend/api.py").read_text(encoding="utf-8")
ACCOUNT_SOURCE = Path("account.html").read_text(encoding="utf-8")
MARKETPLACE_SOURCE = Path("marketplace.html").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    tree = ast.parse(API_SOURCE)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(API_SOURCE, node) or ""
    raise AssertionError(f"function not found: {name}")


def test_ten_thousand_sats_equals_exact_btc():
    assert int(Decimal("0.00010000") * Decimal("100000000")) == 10000


def test_account_rewards_exposes_exact_sats_and_btc_string():
    source = _function_source("account_rewards")
    assert '"available_btc": btc_display(available_btc)' in source
    assert '"available_sats": btc_to_sats(available_btc)' in source
    assert '"amount_sats":btc_to_sats(r[1])' in source


def test_withdrawal_uses_decimal_not_float():
    assert "amount_btc: Decimal" in API_SOURCE
    assert "amount=body.amount_btc" in API_SOURCE


def test_frontends_present_sats_first_reward_labels():
    assert "sats" in ACCOUNT_SOURCE
    assert "btc-secondary" in MARKETPLACE_SOURCE
    assert "formatBtcReward" in MARKETPLACE_SOURCE
