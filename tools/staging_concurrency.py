#!/usr/bin/env python3
"""Staging race gate: two accounts must not acquire the same single-slot challenge."""
import json, os, secrets, threading, urllib.request, urllib.error

BASE=os.environ.get("SATOSHI_HUNT_API","http://127.0.0.1:8000").rstrip("/")
challenge="satoshi-hunt-staging-001"

def call(path,method="GET",data=None,auth=None):
    req=urllib.request.Request(BASE+path,method=method,headers={"Content-Type":"application/json"})
    if auth: req.add_header("Authorization","Bearer "+auth)
    if data is not None: req.data=json.dumps(data).encode()
    try:
        with urllib.request.urlopen(req,timeout=15) as r: return r.status,json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code,json.loads(e.read() or b"{}")

def make_user():
    email="race-"+secrets.token_hex(5)+"@example.com"
    s,d=call("/auth/register","POST",{"email":email,"password":"Race-"+secrets.token_urlsafe(12)})
    assert s==200,(s,d)
    return d["session"]

sessions=[make_user(),make_user()]
workers=[]
for session in sessions:
    s,d=call("/workers","POST",{"label":"staging-race"},session); assert s==200,(s,d)
    workers.append((session,d["id"]))

results=[None,None]
def run(i):
    session,wid=workers[i]
    results[i]=call(f"/marketplace/challenges/{challenge}/run","POST",{"worker_id":wid},session)
threads=[threading.Thread(target=run,args=(i,)) for i in range(2)]
for t in threads:t.start()
for t in threads:t.join()

statuses=[x[0] for x in results]
if statuses.count(200) != 1 or statuses.count(409) + statuses.count(429) != 1:
    raise SystemExit(f"assignment race gate failed: statuses={statuses} results={results}")
print("STAGING_CONCURRENCY=PASS",json.dumps({"statuses":statuses}))
