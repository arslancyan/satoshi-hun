#!/usr/bin/env python3
"""Isolated Satoshi Hunt payout signer.

Private keys never enter this process. Bitcoin Core owns the wallet and performs
PSBT signing. This worker only receives payout intents, asks Bitcoin Core to
create/sign/finalize a PSBT, then submits attestations to the API.
"""

import base64
import json
import os
import time
import urllib.error
import urllib.request
import urllib.parse
from decimal import Decimal

API_URL = os.environ["SATOSHI_HUNT_API_URL"].rstrip("/")
PAYOUT_WORKER_TOKEN = os.environ["PAYOUT_WORKER_TOKEN"]
PAYOUT_SIGNER_TOKEN = os.environ["PAYOUT_SIGNER_TOKEN"]
BITCOIN_RPC_URL = os.environ["BITCOIN_RPC_URL"].rstrip("/")
BITCOIN_RPC_USER = os.environ["BITCOIN_RPC_USER"]
BITCOIN_RPC_PASSWORD = os.environ["BITCOIN_RPC_PASSWORD"]
BITCOIN_RPC_WALLET = os.environ.get("BITCOIN_RPC_WALLET", "").strip()
SIGNER_ID = os.environ.get("PAYOUT_SIGNER_ID", "bitcoin-core-isolated-signer")
POLL_SECONDS = max(2, int(os.environ.get("PAYOUT_POLL_SECONDS", "10")))
FEE_RATE_SAT_VB = Decimal(os.environ.get("PAYOUT_FEE_RATE_SAT_VB", "5"))
MIN_CONFIRMATIONS = int(os.environ.get("PAYOUT_MIN_CONFIRMATIONS", "1"))


def _http_json(url, payload=None, headers=None, timeout=30):
    data = None
    request_headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode()
        request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=data, headers=request_headers, method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def api_post(path, payload, signer=False):
    headers = {
        "X-Payout-Signer-Token" if signer else "X-Payout-Worker-Token":
        PAYOUT_SIGNER_TOKEN if signer else PAYOUT_WORKER_TOKEN
    }
    return _http_json(API_URL + path, payload, headers)


def rpc(method, params=None):
    url = BITCOIN_RPC_URL
    if BITCOIN_RPC_WALLET:
        url += "/wallet/" + urllib.parse.quote(BITCOIN_RPC_WALLET, safe="")
    payload = {"jsonrpc": "1.0", "id": "satoshi-hunt-signer", "method": method, "params": params or []}
    auth = base64.b64encode(f"{BITCOIN_RPC_USER}:{BITCOIN_RPC_PASSWORD}".encode()).decode()
    result = _http_json(url, payload, {"Authorization": "Basic " + auth})
    if result.get("error"):
        raise RuntimeError(f"Bitcoin Core {method} failed: {result['error']}")
    return result["result"]


def create_psbt(destination, amount_btc):
    amount = float(Decimal(str(amount_btc)))
    result = rpc("walletcreatefundedpsbt", [
        [],
        {destination: amount},
        0,
        {
            "add_inputs": True,
            "fee_rate": float(FEE_RATE_SAT_VB),
            "lock_unspents": True,
            "replaceable": True,
        },
        True,
    ])
    return result["psbt"]


def sign_and_finalize(psbt):
    processed = rpc("walletprocesspsbt", [psbt, True, "ALL", False])
    if not processed.get("complete"):
        raise RuntimeError("Bitcoin Core could not fully sign the payout PSBT")
    finalized = rpc("finalizepsbt", [processed["psbt"], True])
    if not finalized.get("complete") or not finalized.get("hex"):
        raise RuntimeError("Bitcoin Core could not finalize the payout PSBT")
    return processed["psbt"], finalized["hex"]


def handle_withdrawal(withdrawal):
    wid = withdrawal["id"]
    amount = withdrawal["amount_btc"]
    destination = withdrawal["payout_address"]
    settlement_status = withdrawal.get("settlement_status", "PSBT_REQUESTED")
    unsigned_psbt = withdrawal.get("unsigned_psbt")
    signed_psbt = withdrawal.get("signed_psbt")
    final_tx_hex = withdrawal.get("final_tx_hex")

    # Recovery is deliberately stateful: never create a second PSBT when the
    # API already has a safe in-flight settlement for this withdrawal.
    if settlement_status == "SIGNED" and final_tx_hex:
        txid = rpc("sendrawtransaction", [final_tx_hex])
    else:
        if settlement_status == "PSBT_READY" and unsigned_psbt:
            psbt = unsigned_psbt
        else:
            psbt = create_psbt(destination, amount)
            api_post(
                f"/internal/payouts/{wid}/psbt",
                {"unsigned_psbt": psbt, "signer_id": SIGNER_ID},
                signer=True,
            )

        signed_psbt, final_tx_hex = sign_and_finalize(psbt)
        api_post(
            f"/internal/payouts/{wid}/signed",
            {
                "signed_psbt": signed_psbt,
                "final_tx_hex": final_tx_hex,
                "signer_id": SIGNER_ID,
            },
            signer=True,
        )
        txid = rpc("sendrawtransaction", [final_tx_hex])

    api_post(
        f"/internal/payouts/{wid}/broadcast",
        {"txid": txid, "broadcaster_id": SIGNER_ID},
        signer=True,
    )
    api_post(f"/internal/payouts/{wid}/settle", {}, signer=True)
    print(f"settled withdrawal={wid} txid={txid}", flush=True)


def main():
    # Fail closed if the configured wallet cannot answer.
    rpc("getwalletinfo")
    while True:
        try:
            result = api_post("/internal/payouts/next", {})
            withdrawal = result.get("withdrawal")
            if not withdrawal:
                time.sleep(POLL_SECONDS)
                continue
            handle_withdrawal(withdrawal)
        except Exception as exc:
            # Never mark a payout paid locally. The API remains the source of truth.
            print(f"signer error: {type(exc).__name__}: {exc}", flush=True)
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
