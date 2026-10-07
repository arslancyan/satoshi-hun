#!/usr/bin/env python3
"""Production smoke checks for Satoshi Hunt public API."""
import json, os, sys, subprocess, urllib.request, urllib.error

BASE = os.environ.get("SATOSHI_HUNT_API", "https://satoshi-hunt-api-production.up.railway.app").rstrip("/")
ORIGIN = os.environ.get("SATOSHI_HUNT_FRONTEND_ORIGIN", "https://arslancyan.github.io")
EXPECTED_COMMIT = os.environ.get("SATOSHI_HUNT_EXPECTED_COMMIT", "").strip()

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
if EXPECTED_COMMIT:
    ok &= check(
        "deployed commit",
        b.get("commit") == EXPECTED_COMMIT,
        f"expected={EXPECTED_COMMIT} actual={b.get('commit')}",
    )
ok &= check("security headers", s==200 and h.get("X-Content-Type-Options")=="nosniff" and h.get("X-Frame-Options")=="DENY" and bool(h.get("X-Request-ID")), f"{s} headers={h}")
s,h,b=request("/ready")
ok &= check("readiness", s==200 and b.get("ready") is True and b.get("database") is True and b.get("redis") is True and b.get("jwt") is True, f"{s} {b}")
s,h,b=request("/marketplace/challenges")
ok &= check("public marketplace accessible", s==200 and isinstance(b.get("challenges"), list), f"{s} {b}")
curl = subprocess.run(
    ["curl", "-sS", "-i", "-X", "OPTIONS", BASE + "/auth/login",
     "-H", f"Origin: {ORIGIN}",
     "-H", "Access-Control-Request-Method: POST",
     "-H", "Access-Control-Request-Headers: content-type"],
    capture_output=True, text=True, timeout=15, check=False,
)
curl_headers = {}
for line in curl.stdout.splitlines():
    if ":" in line:
        key, value = line.split(":", 1)
        curl_headers[key.strip().lower()] = value.strip()
cors = (
    curl.returncode == 0
    and curl_headers.get("access-control-allow-origin") == ORIGIN
    and "POST" in curl_headers.get("access-control-allow-methods", "")
)
s = 200 if curl.returncode == 0 else 0
h = curl_headers
b = {}

ok &= check("GitHub Pages CORS preflight", cors, f"{s} origin={h.get('Access-Control-Allow-Origin','missing')} methods={h.get('Access-Control-Allow-Methods','missing')}")
s,h,b=request("/account/payout-address","PUT",{"btc_payout_address":"not-a-bitcoin-address"})
ok &= check("invalid wallet rejected", s in (401,422), f"{s} {b}")
print("SMOKE_RESULT="+("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)

# Production gate: browser-preflight validation remains enabled.
