"""Challenge verification contracts for Satoshi Hunt.

Only explicitly public reward challenges should register adapters here.
No adapter may read private keys, seed phrases, wallet credentials, or hidden
challenge material.
"""
from datetime import datetime, timezone
import hashlib

VALID={"OPEN + FUNDED","OPEN + UNFUNDED","SOLVED + FUNDED","SOLVED + EMPTY","UNKNOWN"}

class VerificationResult:
    def __init__(self, verified, reason, candidate_hash):
        self.verified = verified
        self.reason = reason
        self.candidate_hash = candidate_hash
        self.checked_at = datetime.now(timezone.utc).isoformat()

    def as_dict(self):
        return {
            "verified": self.verified,
            "reason": self.reason,
            "candidate_hash": self.candidate_hash,
            "checked_at": self.checked_at,
        }


class ChallengeAdapter:
    challenge_type = "unknown"

    def verify(self, record, candidate):
        raise NotImplementedError


ADAPTERS = {}

def normalize(record):
    q=dict(record)
    q["id"]=str(q.get("id",""))
    q["reward_btc"]=max(0.0,float(q.get("reward_btc",0) or 0))
    q["balance_btc"]=max(0.0,float(q.get("balance_btc",0) or 0))
    q["status"]=q.get("status") if q.get("status") in VALID else "UNKNOWN"
    q["rules"]=str(q.get("rules",""))
    q["provenance"]=q.get("provenance")
    q["verification"]=q.get("verification")
    return q


def register_adapter(adapter):
    if not getattr(adapter, "challenge_type", None) or adapter.challenge_type == "unknown":
        raise ValueError("Adapter must declare a concrete challenge_type")
    if adapter.challenge_type in ADAPTERS:
        raise ValueError(f"Adapter already registered: {adapter.challenge_type}")
    ADAPTERS[adapter.challenge_type] = adapter
    return adapter


def classify(record):
    balance=float(record.get("balance_btc",0) or 0)
    solved=record.get("solved",None)
    if solved is True and balance<=0:return "SOLVED + EMPTY"
    if solved is True and balance>0:return "SOLVED + FUNDED"
    if solved is False and balance>0:return "OPEN + FUNDED"
    if solved is False and balance<=0:return "OPEN + UNFUNDED"
    return record.get("status") if record.get("status") in VALID else "UNKNOWN"


def eligible(record):
    return (
        classify(record) == "OPEN + FUNDED"
        and record.get("rules") == "public-reward-challenge"
        and bool(record.get("provenance"))
        and bool(record.get("verification"))
    )


def verify_candidate(record, candidate):
    candidate_hash = hashlib.sha256(str(candidate).encode()).hexdigest()
    if not eligible(record):
        return VerificationResult(False, "Challenge is not fully verified for solver use.", candidate_hash).as_dict()

    adapter = ADAPTERS.get(str(record.get("type", "unknown")))
    if not adapter:
        return VerificationResult(False, "No challenge-specific verifier registered.", candidate_hash).as_dict()

    try:
        result = adapter.verify(record, candidate)
    except Exception as exc:
        return VerificationResult(False, f"Verifier error: {type(exc).__name__}", candidate_hash).as_dict()

    if not isinstance(result, bool):
        return VerificationResult(False, "Verifier returned an invalid result.", candidate_hash).as_dict()

    return VerificationResult(result, "Verified by registered public-challenge adapter." if result else "Candidate rejected by challenge adapter.", candidate_hash).as_dict()


class HashCommitmentAdapter(ChallengeAdapter):
    """Reference adapter for public challenges whose published verification
    rule is an exact candidate-hash commitment.

    It never receives private keys or wallet credentials. Production adapters
    must be challenge-specific and independently reviewed.
    """
    challenge_type = "hash-commitment"

    def verify(self, record, candidate_hash):
        expected = str(record.get("verification", {}).get("expected_candidate_hash", "")).lower()
        supplied = str(candidate_hash).lower()
        return bool(expected) and supplied == expected


register_adapter(HashCommitmentAdapter())


def verify_candidate_hash(record, candidate_hash):
    """Verify a worker-submitted candidate hash without receiving candidate material."""
    normalized = normalize(record)
    candidate_hash = str(candidate_hash)
    if not eligible(normalized):
        return VerificationResult(False, "Challenge is not fully verified for solver use.", candidate_hash).as_dict()
    adapter = ADAPTERS.get(str(normalized.get("type", "unknown")))
    if not adapter:
        return VerificationResult(False, "No challenge-specific verifier registered.", candidate_hash).as_dict()
    try:
        result = adapter.verify(normalized, candidate_hash)
    except Exception as exc:
        return VerificationResult(False, f"Verifier error: {type(exc).__name__}", candidate_hash).as_dict()
    if not isinstance(result, bool):
        return VerificationResult(False, "Verifier returned an invalid result.", candidate_hash).as_dict()
    return VerificationResult(
        result,
        "Verified by registered public-challenge adapter." if result else "Candidate rejected by challenge adapter.",
        candidate_hash,
    ).as_dict()
