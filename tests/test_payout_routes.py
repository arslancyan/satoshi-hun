from pathlib import Path

def test_payout_routes_and_limits_are_present():
    api=Path("backend/api.py").read_text()
    assert '@app.get("/admin/withdrawals")' in api
    assert '@app.post("/admin/withdrawals/{withdrawal_id}/processing")' in api
    assert '@app.post("/admin/withdrawals/{withdrawal_id}/complete")' in api
    assert '@app.post("/internal/payouts/next")' in api
    assert '@app.post("/internal/payouts/{withdrawal_id}/complete")' in api
    assert "MAX_SINGLE_PAYOUT_BTC" in api
    assert "MAX_DAILY_PAYOUT_BTC" in api
    assert "PAYOUT_RETRY_AFTER_MINUTES" in api
    assert "validate_external_txid" in api

def test_payout_completion_requires_external_txid():
    api=Path("backend/api.py").read_text()
    start=api.index("class WithdrawalComplete")
    end=api.index("class PayoutAddressUpdate",start)
    flow=api[start:end]
    assert "min_length=3" in flow
    assert "validate_external_txid" in flow
    assert "status='PAID'" in flow

def test_payout_worker_fails_closed_without_token():
    api=Path("backend/api.py").read_text()
    assert 'if not PAYOUT_WORKER_TOKEN' in api
