import hashlib,json,sys
from datetime import datetime,timezone
from verifier import normalize,classify,eligible

VALID={"OPEN + FUNDED","OPEN + UNFUNDED","SOLVED + FUNDED","SOLVED + EMPTY","UNKNOWN"}

def canonical_record(record):
    return json.dumps(record,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()

def fingerprint(record):
    return hashlib.sha256(canonical_record(record)).hexdigest()

def audit(path="puzzles.json"):
    data=json.load(open(path,encoding="utf8")); errors=[]; ids=set()
    if data.get("schema_version",0) < 3:
        errors.append("registry: schema_version must be >= 3")
    if not data.get("source"):
        errors.append("registry: missing source")
    for raw in data.get("puzzles",[]):
        p=normalize(raw); pid=p["id"]
        if not pid or pid in ids: errors.append(f"{pid or '?'}: missing/duplicate id")
        ids.add(pid)
        if p["status"] not in VALID: errors.append(f"{pid}: invalid status")
        if p["status"]=="OPEN + FUNDED" and p["balance_btc"]<=0: errors.append(f"{pid}: funded but zero balance")
        if p["status"]=="OPEN + UNFUNDED" and p["balance_btc"]>0: errors.append(f"{pid}: unfunded but positive balance")
        if p["status"]=="SOLVED + EMPTY" and p["balance_btc"]>0: errors.append(f"{pid}: solved-empty but positive balance")
        if p["reward_btc"]<p["balance_btc"]: errors.append(f"{pid}: balance exceeds recorded reward")
        if p.get("provenance") and not isinstance(p["provenance"],dict):
            errors.append(f"{pid}: provenance must be an object")
        if p.get("verification") and not isinstance(p["verification"],dict):
            errors.append(f"{pid}: verification must be an object")
        if eligible(p):
            prov=p["provenance"]; ver=p["verification"]
            if not prov.get("url") or not prov.get("checked_at"):
                errors.append(f"{pid}: eligible record missing provenance url/checked_at")
            if not ver.get("method") or not ver.get("checked_at"):
                errors.append(f"{pid}: eligible record missing verification method/checked_at")
            if not ver.get("fingerprint"):
                errors.append(f"{pid}: eligible record missing verification fingerprint")
    print("AUDIT OK" if not errors else "\n".join(errors)); return 0 if not errors else 1

if __name__=="__main__":
    sys.exit(audit())
