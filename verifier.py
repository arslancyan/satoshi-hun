"""Status and eligibility guards for public reward challenges."""
VALID={"OPEN + FUNDED","OPEN + UNFUNDED","SOLVED + FUNDED","SOLVED + EMPTY","UNKNOWN"}
def classify(record):
    balance=float(record.get("balance_btc",0) or 0); solved=record.get("solved",None)
    if solved is True and balance<=0:return "SOLVED + EMPTY"
    if solved is True and balance>0:return "SOLVED + FUNDED"
    if solved is False and balance>0:return "OPEN + FUNDED"
    if solved is False and balance<=0:return "OPEN + UNFUNDED"
    return record.get("status") if record.get("status") in VALID else "UNKNOWN"
def eligible(record):
    return classify(record)=="OPEN + FUNDED" and bool(record.get("rules"))
def verify_candidate(record,candidate):
    return {"verified":False,"reason":"No challenge-specific verifier registered."}
