from economy import split_reward, validate_reward_event
from verifier import verify_candidate_hash
from verifier import eligible
from challenge_adapters.peter_todd_hash_collision import ADAPTER as PeterToddHashCollisionAdapter

def main():
    record = {
        "id":"STAGING-HASH-001",
        "type":"hash-commitment",
        "reward_btc":0.01,
        "balance_btc":0.01,
        "status":"OPEN + FUNDED",
        "rules":"public-reward-challenge",
        "provenance":{"url":"https://example.com/challenge","source_id":"STAGING-HASH-001","checked_at":"2026-10-06T00:00:00Z"},
        "verification":{
            "method":"hash-commitment",
            "source_id":"STAGING-HASH-001",
            "checked_at":"2026-10-06T00:00:00Z",
            "fingerprint":"staging",
            "expected_candidate_hash":"abc123",
            "funding_match":True,
            "verification_stale":False,
        },
    }
    verification = verify_candidate_hash(record,"abc123")
    if not verification["verified"]:
        raise SystemExit("FAIL: verifier rejected staging candidate")

    split = split_reward(record["reward_btc"])
    if not validate_reward_event({
        "gross_reward_btc":split["gross"],
        "worker_share_btc":split["worker_share"],
        "platform_fee_btc":split["platform_fee"],
    }):
        raise SystemExit("FAIL: reward ledger split is invalid")

    # A mismatch between advertised and verified funding is never runnable.
    mismatch = dict(record)
    mismatch["balance_btc"] = 0.009
    mismatch["verification"] = dict(record["verification"], funding_match=False)
    if eligible(mismatch):
        raise SystemExit("FAIL: funding mismatch passed eligibility")

    real_record = {
        "id":"peter-todd-hash-collision-bounties",
        "type":"hash-collision",
        "reward_btc":0.59364885,
        "balance_btc":0.59364885,
        "status":"OPEN + FUNDED",
        "rules":"public-reward-challenge",
        "provenance":{
            "url":"https://github.com/floflo777/open-crypto-puzzles",
            "source_id":"peter-todd-hash-collision-bounties",
            "checked_at":"2026-10-06",
        },
        "verification":{
            "method":"published-hash-collision-rule",
            "source_id":"peter-todd-hash-collision-bounties",
            "checked_at":"2026-10-06",
            "fingerprint":"four-live-escrows-public-record",
            "funding_match":True,
            "verification_stale":False,
        },
    }
    real = PeterToddHashCollisionAdapter.verify(real_record,"sha256:00:01")
    if real:
        raise SystemExit("FAIL: invalid public collision candidate was accepted")

    print("PASS: public challenge -> funding gate -> verifier -> reward accounting contract")

if __name__ == "__main__":
    main()
