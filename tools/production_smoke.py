#!/usr/bin/env python3
"""Production smoke checks for Satoshi Hunt public API."""
import json, os, sys, urllib.request, urllib.error

BASE = os.environ.get("SATOSHI_HUNT_API", "https://satoshi-hunt-api-production.up.railway.app").rstrip("/")
ORIGIN = os.environ.get("SATOSHI_HUNT_FRONTEND_ORIGIN", "https://arslancyan.github.io")

def request(path, method="GET", data=None, headers=None):
    body = None if data is None else json.dumps(data).encode()
    h = {"Content-Type":"application/json", "Origin": ORIGIN}
    if headers: h.update(headers)
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+path, data=body, method=method, headers=h), timeout=15) as r:
            raw = r.read().decode(errors="replace")
            try: payload = json.loads(raw) if raw else {}
            except Exception: payload = {"raw": raw}
            return r.status, dict(r.headers), payload
    except urllib.error.HTTPError as e:
        raw=e.read().decode(errors="replace")
        try: payload=json.loads(raw) if raw else {}
        except Exception: payload={"raw":raw}
        return e.code, dict(e.headers), payload

def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    return ok

ok=True
s,h,b=request("/health")
ok &= check("health", s==200 and b.get("ok") is True and b.get("custody")=="non-custodial", f"{s} {b}")
s,h,b=request("/ready")
ok &= check("readiness", s==200 and b.get("ready") is True and b.get("database") is True and b.get("redis") is True, f"{s} {b}")
s,h,b=request("/marketplace/challenges")
ok &= check("unauthenticated marketplace denied", s==401, f"{s} {b}")
s,h,b=request("/auth/login","OPTIONS",headers={"Origin":ORIGIN,"Access-Control-Request-Method":"POST","Access-Control-Request-Headers":"content-type"})
cors = h.get("Access-Control-Allow-Origin")==ORIGIN and "POST" in h.get("Access-Control-Allow-Methods","")
ok &= check("GitHub Pages CORS preflight", cors, f"{s} origin={h.get('Access-Control-Allow-Origin','missing')} methods={h.get('Access-Control-Allow-Methods','missing')}")
s,h,b=request("/account/payout-address","PUT",{"btc_payout_address":"not-a-bitcoin-address"})
ok &= check("invalid wallet rejected", s in (401,422), f"{s} {b}")
print("SMOKE_RESULT="+("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)

# Production gate: browser-preflight validation remains enabled.
