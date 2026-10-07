from challenge_registry_policy import queue_gate


def base_record():
    return {
        "rules": "public-reward-challenge",
        "status": "OPEN + FUNDED",
        "balance_btc": 0.1,
        "verification": {
            "funding_match": True,
            "verification_stale": False,
            "execution_mode": "COMPUTE",
            "adapter_audited": True,
            "adapter_runnable": True,
        },
        "payout": {
            "permissionless": True,
            "automatic_chain_claim": True,
        },
    }


def test_fully_verified_runnable_record_enters_queue():
    result = queue_gate(base_record())
    assert result["eligible"] is True
    assert result["reasons"] == []


def test_unfunded_record_is_blocked():
    record = base_record()
    record["balance_btc"] = 0
    result = queue_gate(record)
    assert result["eligible"] is False
    assert "no_positive_balance" in result["reasons"]


def test_verify_only_adapter_is_blocked():
    record = base_record()
    record["verification"]["execution_mode"] = "VERIFY"
    record["verification"]["adapter_runnable"] = False
    result = queue_gate(record)
    assert result["eligible"] is False
    assert "execution_mode_not_compute" in result["reasons"]
    assert "adapter_not_runnable" in result["reasons"]


def test_missing_audit_provenance_is_blocked():
    record = base_record()
    record["verification"]["adapter_audited"] = False
    result = queue_gate(record)
    assert result["eligible"] is False
    assert "adapter_not_audited" in result["reasons"]
