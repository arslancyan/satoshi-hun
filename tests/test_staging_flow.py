from decimal import Decimal
from economy import split_reward, validate_reward_event
from verifier import verify_candidate_hash

def challenge():
    return {"id":"STAGING-HASH-001","type":"hash-commitment","reward_btc":0.01,"balance_btc":0.01,"status":"OPEN + FUNDED","rules":"public-reward-challenge","provenance":{"url":"https://example.com/challenge","source_id":"STAGING-HASH-001","checked_at":"2026-10-06T00:00:00Z"},"verification":{"method":"hash-commitment","source_id":"STAGING-HASH-001","fingerprint":"staging","expected_candidate_hash":"abc123","funding_match":True,"verification_stale":False}}

def test_staging_happy_path_contract():
    result=verify_candidate_hash(challenge(),"abc123")
    assert result["verified"] is True, result
    split=split_reward(0.01)
    assert validate_reward_event({"gross_reward_btc":split["gross"],"worker_share_btc":split["worker_share"],"platform_fee_btc":split["platform_fee"]})
    assert split["worker_share"] == Decimal("0.00850000")
    assert split["platform_fee"] == Decimal("0.00150000")

def test_staging_rejects_unfunded_challenge():
    record=challenge(); record["status"]="OPEN + UNFUNDED"
    assert verify_candidate_hash(record,"abc123")["verified"] is False

def test_staging_rejects_missing_provenance():
    record=challenge(); record["provenance"]={}
    assert verify_candidate_hash(record,"abc123")["verified"] is False

def test_staging_rejects_wrong_candidate():
    assert verify_candidate_hash(challenge(),"wrong")["verified"] is False
