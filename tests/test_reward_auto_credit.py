from pathlib import Path


def test_reward_auto_credit_and_withdrawal_contract():
    api=Path("backend/api.py").read_text()
    schema=Path("backend/schema.sql").read_text()
    assert "def auto_credit_verified_claim" in api
    assert "AUTO_REWARD_CREDITED" in api
    assert "withdrawal_queued" in api
    assert "reward_balances" in schema
    assert "reward_ledger" in schema
    assert "withdrawal_requests" in schema


def test_reward_split_remains_eighty_five_fifteen():
    settlement=Path("settlement.py").read_text()
    assert 'WORKER_SHARE = Decimal("0.85")' in settlement
    assert 'PLATFORM_SHARE = Decimal("0.15")' in settlement


def test_no_private_key_signing_in_reward_flow():
    api=Path("backend/api.py").read_text().lower()
    assert "private key" not in api
    assert "seed phrase" not in api
    assert "signrawtransaction" not in api
    assert "sendrawtransaction" not in api


def test_account_security_and_payout_validation_contract():
    api=Path("backend/api.py").read_text()
    migration=Path("backend/migrations/007_account_security.sql").read_text()
    assert "def hash_password" in api
    assert "def verify_password" in api
    assert '@app.post("/auth/register")' in api
    assert '@app.post("/auth/login")' in api
    assert "valid_btc_mainnet_address" in api
    assert "password_hash" in migration
    assert "PBKDF2" in migration


def test_non_custodial_withdrawal_never_stores_signing_material():
    api=Path("backend/api.py").read_text().lower()
    assert "private key" not in api
    assert "seed phrase" not in api
    assert "wif" not in api
    assert "signrawtransaction" not in api
    assert "sendrawtransaction" not in api
