from economy import split_reward, validate_reward_event
from verifier import verify_candidate_hash

def main():
    record={"id":"STAGING-HASH-001","type":"hash-commitment","reward_btc":0.01,"balance_btc":0.01,"status":"OPEN + FUNDED","rules":"public-reward-challenge","provenance":{"url":"https://example.com/challenge","source_id":"STAGING-HASH-001"},"verification":{"method":"hash-commitment","source_id":"STAGING-HASH-001","fingerprint":"staging","expected_candidate_hash":"abc123"}}
    verification=verify_candidate_hash(record,"abc123")
    if not verification["verified"]: raise SystemExit("FAIL: verifier rejected staging candidate")
    split=split_reward(record["reward_btc"])
    if not validate_reward_event({"gross_reward_btc":split["gross"],"worker_share_btc":split["worker_share"],"platform_fee_btc":split["platform_fee"]}): raise SystemExit("FAIL: reward ledger split is invalid")
    print("PASS: challenge -> verifier -> reward accounting contract")

if __name__ == "__main__": main()
