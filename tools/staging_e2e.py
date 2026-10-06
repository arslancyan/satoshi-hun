import json, os, secrets, urllib.request, urllib.error

BASE=os.environ.get("SATOSHI_HUNT_API","http://127.0.0.1:8000").rstrip("/")
def call(path, method="GET", data=None, auth=None, worker=None):
    body=None if data is None else json.dumps(data).encode()
    headers={"Content-Type":"application/json"}
    if auth: headers["Authorization"]="Bearer "+auth
    if worker: headers["Authorization"]="Worker "+worker
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+path,data=body,method=method,headers=headers),timeout=10) as r:
            return r.status,json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code,json.loads(e.read() or b"{}")

def ok(name,status,data,want=200):
    good=status==want
    print(("[PASS] " if good else "[FAIL] ")+name+" "+str(status)+" "+json.dumps(data))
    if not good: raise SystemExit(1)
    return data

email="staging-"+secrets.token_hex(4)+"@example.com"
password="Staging-"+secrets.token_urlsafe(12)
session=ok("signup",*call("/auth/register","POST",{"email":email,"password":password}))["session"]
session=ok("login",*call("/auth/login","POST",{"email":email,"password":password}))["session"]
ok("account",*call("/me",auth=session))
ok("wallet",*call("/account/payout-address","PUT",{"btc_payout_address":"1BoatSLRHtKNngkdXEeobR76b53LETtpyT"},session))
worker=ok("worker",*call("/workers","POST",{"label":"staging-e2e"},session))
market=ok("marketplace",*call("/marketplace/challenges"))["challenges"]
challenge=next(x for x in market if x["challenge_id"]=="satoshi-hunt-staging-001")
run=ok("run",*call("/marketplace/challenges/satoshi-hunt-staging-001/run","POST",{"worker_id":worker["id"]},session))
wid=worker["id"]; wt=worker["worker_token"]; aid=run["assignment_id"]; job=run["job_id"]
ok("start",*call("/assignments/"+aid+"/start","POST",worker=wt))
ok("heartbeat",*call("/assignments/"+aid+"/heartbeat","POST",worker=wt))
claim=ok("verify known solution",*call("/jobs/"+job+"/claims","POST",{"assignment_id":aid,"worker_id":wid,"candidate_hash":"b54609333c7f5082f8e8eb408e40a59d73e9fbe9f546c2adf75347cd941bd22d","result_status":"TESTED","cpu_seconds":1},worker=wt))
if claim.get("verified") is not True: raise SystemExit(1)
rewards=ok("reward",*call("/account/rewards",auth=session))
if rewards["available_btc"] != 0: raise SystemExit(1)
if not rewards["withdrawals"] or rewards["withdrawals"][0]["status"]!="QUEUED": raise SystemExit(1)
ok("idempotent second claim",*call("/jobs/"+job+"/claims","POST",{"assignment_id":aid,"worker_id":wid,"candidate_hash":"b54609333c7f5082f8e8eb408e40a59d73e9fbe9f546c2adf75347cd941bd22d","result_status":"TESTED","cpu_seconds":1},worker=wt))
print("STAGING_E2E=PASS")
