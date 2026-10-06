import json,sys
VALID={"OPEN + FUNDED","OPEN + UNFUNDED","SOLVED + FUNDED","SOLVED + EMPTY","UNKNOWN"}
def audit(path="puzzles.json"):
    data=json.load(open(path,encoding="utf8")); errors=[]
    for p in data.get("puzzles",[]):
        if p.get("status") not in VALID: errors.append(f'{p.get("id")}: invalid status')
        if float(p.get("balance_btc",0))<0 or float(p.get("reward_btc",0))<0: errors.append(f'{p.get("id")}: negative amount')
        if p.get("status")=="OPEN + FUNDED" and float(p.get("balance_btc",0))<=0: errors.append(f'{p.get("id")}: funded but zero balance')
    print("OK" if not errors else "\n".join(errors)); return 0 if not errors else 1
if __name__=="__main__": sys.exit(audit())
