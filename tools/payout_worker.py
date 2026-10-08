import json
import os
import time
import urllib.error
import urllib.request

API=os.environ.get("SATOSHI_HUNT_API","").rstrip("/")
WORKER_TOKEN=os.environ.get("PAYOUT_WORKER_TOKEN","").strip()
EXECUTOR_URL=os.environ.get("PAYOUT_EXECUTOR_URL","").rstrip("/")
EXECUTOR_TOKEN=os.environ.get("PAYOUT_EXECUTOR_TOKEN","").strip()
POLL_SECONDS=max(5,int(os.environ.get("PAYOUT_POLL_SECONDS","15")))

def post(url, payload, token, header_name):
    body=json.dumps(payload).encode()
    req=urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type":"application/json",header_name:token},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read() or b"{}")

def main():
    # Fail closed: this worker must never move funds without an explicitly
    # configured external signer/executor.
    if not API or not WORKER_TOKEN or not EXECUTOR_URL or not EXECUTOR_TOKEN:
        raise SystemExit("Payout worker disabled: API, payout worker token, executor URL and executor token are required.")
    while True:
        try:
            status, data=post(API+"/internal/payouts/next",{},WORKER_TOKEN,"X-Payout-Worker-Token")
            withdrawal=data.get("withdrawal")
            if not withdrawal:
                time.sleep(POLL_SECONDS)
                continue

            payload={
                "withdrawal_id":withdrawal["id"],
                "amount_btc":withdrawal["amount_btc"],
                "payout_address":withdrawal["payout_address"],
                "idempotency_key":withdrawal["idempotency_key"],
            }
            if withdrawal.get("payout_mode") == "DIRECT_PUBLIC_ESCROW":
                payload.update({
                    "challenge_id": withdrawal.get("puzzle_id"),
                    "claim_nonce": withdrawal.get("claim_nonce"),
                    "escrow_address": withdrawal.get("escrow_address"),
                    "witness_script_hex": withdrawal.get("witness_script_hex"),
                })
                endpoint=EXECUTOR_URL + "/escrow-payout"
            else:
                endpoint=EXECUTOR_URL + "/payout"
            status, result=post(endpoint,payload,EXECUTOR_TOKEN,"Authorization")
            txid=str(result.get("txid","")).strip()
            if not txid:
                raise RuntimeError("Payout executor returned no txid")

            post(API+"/internal/payouts/"+withdrawal["id"]+"/complete",
                 {"external_reference":txid},WORKER_TOKEN,"X-Payout-Worker-Token")
            print(json.dumps({"paid":withdrawal["id"],"txid":txid},sort_keys=True),flush=True)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
            # Leave PROCESSING withdrawals untouched on executor/network failure.
            # The API safely retries stale PROCESSING rows after its configured
            # retry window; executor idempotency must be keyed by withdrawal id.
            print(json.dumps({"payout_error":type(exc).__name__,"detail":str(exc)[:200]},sort_keys=True),flush=True)
            time.sleep(POLL_SECONDS)

if __name__=="__main__":
    main()
