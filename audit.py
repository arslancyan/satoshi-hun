import json,sys
from verifier import normalize,classify,eligible
VALID={"OPEN + FUNDED","OPEN + UNFUNDED","SOLVED + FUNDED","SOLVED + EMPTY","UNKNOWN"}
def audit(path="puzzles.json"):
 data=json.load(open(path,encoding="utf8")); errors=[]; ids=set()
 for raw in data.get("puzzles",[]):
  p=normalize(raw); pid=p["id"]
  if not pid or pid in ids: errors.append(f"{pid or '?'}: missing/duplicate id")
  ids.add(pid)
  if p["status"] not in VALID: errors.append(f"{pid}: invalid status")
  if p["status"]=="OPEN + FUNDED" and p["balance_btc"]<=0: errors.append(f"{pid}: funded but zero balance")
  if p["status"]=="OPEN + UNFUNDED" and p["balance_btc"]>0: errors.append(f"{pid}: unfunded but positive balance")
  if p["status"]=="SOLVED + EMPTY" and p["balance_btc"]>0: errors.append(f"{pid}: solved-empty but positive balance")
  if p["reward_btc"]<p["balance_btc"]: errors.append(f"{pid}: balance exceeds recorded reward")
 print("AUDIT OK" if not errors else "\n".join(errors)); return 0 if not errors else 1
if __name__=="__main__": sys.exit(audit())
