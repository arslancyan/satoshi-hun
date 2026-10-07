#!/usr/bin/env python3
import json, os, urllib.request, urllib.error
BASE=os.environ.get("SATOSHI_HUNT_API","http://127.0.0.1:8000").rstrip("/")
email=os.environ.get("STAGING_OWNER_EMAIL","owner@example.com")
password=os.environ.get("STAGING_OWNER_PASSWORD","Staging-Owner-Only-2026!")
prefix=os.environ.get("MOCK_PAYOUT_TX_PREFIX","staging-mock-")

def call(path,method="GET",data=None,token=None):
    req=urllib.request.Request(BASE+path,method=method,headers={"Content-Type":"application/json"})
    if token:req.add_header("Authorization","Bearer "+token)
    if data is not None:req.data=json.dumps(data).encode()
    try:
        with urllib.request.urlopen(req,timeout=15) as r:return r.status,json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:return e.code,json.loads(e.read() or b"{}")

s,d=call("/auth/login","POST",{"email":email,"password":password})
if s!=200: raise SystemExit(f"owner login failed: {s} {d}")
s,d=call("/admin/withdrawals",token=d["session"])
if s!=200: raise SystemExit(f"admin withdrawals failed: {s} {d}")
matches=[x for x in d.get("withdrawals",[]) if str(x.get("external_reference") or "").startswith(prefix) and x.get("status")=="PAID"]
if not matches: raise SystemExit("no staging payout reached PAID with mock external reference")
print("STAGING_PAYOUT=PASS",json.dumps({"paid_count":len(matches)}))
