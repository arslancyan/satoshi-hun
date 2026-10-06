import json,hashlib,time,uuid
from datetime import datetime,timezone

STATUSES={"OPEN + FUNDED","OPEN + UNFUNDED","SOLVED + FUNDED","SOLVED + EMPTY","UNKNOWN"}

def normalize(p):
    q=dict(p)
    q["id"]=str(q.get("id",""))
    q["reward_btc"]=max(0.0,float(q.get("reward_btc",0) or 0))
    q["balance_btc"]=max(0.0,float(q.get("balance_btc",0) or 0))
    q["status"]=q.get("status") if q.get("status") in STATUSES else "UNKNOWN"
    q["rules"]=str(q.get("rules",""))
    q["provenance"]=q.get("provenance")
    q["verification"]=q.get("verification")
    return q

def classify(p):
    p=normalize(p); b=p["balance_btc"]; solved=p.get("solved")
    if solved is True: return "SOLVED + EMPTY" if b<=0 else "SOLVED + FUNDED"
    if solved is False: return "OPEN + FUNDED" if b>0 else "OPEN + UNFUNDED"
    return p["status"]

def eligible(p):
    provenance = p.get("provenance")
    verification = p.get("verification")
    return (
        classify(p) == "OPEN + FUNDED"
        and p.get("rules") == "public-reward-challenge"
        and isinstance(provenance, dict)
        and all(str(provenance.get(k, "")).strip() for k in ("url", "source_id", "checked_at"))
        and isinstance(verification, dict)
        and all(str(verification.get(k, "")).strip() for k in ("method", "source_id", "checked_at", "fingerprint"))
    )

def make_job(p):
    p=normalize(p)
    if not eligible(p): raise ValueError("Puzzle is not eligible for solver queue")
    return {"job_id":str(uuid.uuid4()),"created_at":datetime.now(timezone.utc).isoformat(),
            "puzzle_id":p["id"],"puzzle_type":p.get("type","unknown"),
            "limits":{"cpu_seconds":30,"max_candidates":5000},
            "scope":"public-reward-challenge"}

def verify_candidate(p,candidate):
    return {"verified":False,"reason":"challenge-specific verifier required",
            "candidate_hash":hashlib.sha256(str(candidate).encode()).hexdigest(),
            "checked_at":datetime.now(timezone.utc).isoformat()}
