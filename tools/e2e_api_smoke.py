"""Ephemeral production API smoke test. Creates a synthetic account and never logs its password/token."""
import json
import secrets
import time
import urllib.error
import urllib.request

API = "https://satoshi-hunt-api-production.up.railway.app"
EMAIL = f"e2e-{int(time.time())}@example.com"
PASSWORD = "E2E-" + secrets.token_urlsafe(24) + "-SatoshiHunt"


def call(path, method="GET", payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode()
    req_headers = {"Content-Type": "application/json"}
    req_headers.update(headers or {})
    req = urllib.request.Request(API + path, data=data, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode()
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = body
        return exc.code, parsed


def require(status, data, expected=200):
    if status != expected:
        raise RuntimeError(f"unexpected HTTP {status}: {data}")
    return data


def main():
    status, register = call("/auth/register", "POST", {"email": EMAIL, "password": PASSWORD})
    require(status, register)
    status, login = call("/auth/login", "POST", {"email": EMAIL, "password": PASSWORD})
    require(status, login)
    token = login["session"]
    auth = {"Authorization": "Bearer " + token}

    status, me = call("/me", headers=auth)
    require(status, me)

    status, wallet = call(
        "/account/payout-address",
        "PUT",
        {"btc_payout_address": "1BoatSLRHtKNngkdXEeobR76b53LETtpyT"},
        {**auth, "Idempotency-Key": "e2e-wallet-1"},
    )
    require(status, wallet)

    status, worker = call(
        "/workers",
        "POST",
        {"label": "e2e-worker"},
        {**auth, "Idempotency-Key": "e2e-worker-1"},
    )
    require(status, worker)

    status, workers = call("/workers", headers=auth)
    require(status, workers)

    status, challenges = call("/marketplace/challenges", headers=auth)
    require(status, challenges)

    run = None
    heartbeat = None
    assignments = None
    if challenges.get("challenges"):
        challenge = challenges["challenges"][0]
        status, run = call(
            f"/marketplace/challenges/{challenge['challenge_id']}/run",
            "POST",
            {"worker_id": worker["id"]},
            {**auth, "Idempotency-Key": "e2e-run-1"},
        )
        require(status, run)

        worker_auth = {"Authorization": "Worker " + worker["worker_token"]}
        status, heartbeat = call(
            f"/workers/{worker['id']}/heartbeat",
            "POST",
            None,
            {**worker_auth, "Idempotency-Key": "e2e-heartbeat-1"},
        )
        require(status, heartbeat)

        status, assignments = call(
            f"/workers/{worker['id']}/assignments",
            headers=worker_auth,
        )
        require(status, assignments)

    print(json.dumps({
        "ok": True,
        "register": True,
        "login": True,
        "me": {"id": me["id"], "email": me["email"]},
        "wallet": wallet,
        "worker": {"id": worker["id"], "status": worker["status"]},
        "worker_count": len(workers),
        "real_challenge_count": len(challenges.get("challenges", [])),
        "challenge": (
            {
                "id": challenges["challenges"][0]["challenge_id"],
                "title": challenges["challenges"][0]["title"],
                "balance_btc": challenges["challenges"][0]["balance_btc"],
                "funding_match": challenges["challenges"][0]["funding_match"],
                "verification_stale": challenges["challenges"][0]["verification_stale"],
                "permissionless": challenges["challenges"][0]["payout"].get("permissionless"),
                "automatic_chain_claim": challenges["challenges"][0]["payout"].get("automatic_chain_claim"),
            }
            if challenges.get("challenges") else None
        ),
        "run": run,
        "heartbeat": heartbeat,
        "assignments": assignments,
    }))
    

if __name__ == "__main__":
    main()
