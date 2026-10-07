from worker import challenge_execution_allowed


def base_challenge():
    return {
        "rules": "public-reward-challenge",
        "status": "OPEN + FUNDED",
        "verification": {
            "execution_mode": "COMPUTE",
            "adapter_audited": True,
            "adapter_runnable": True,
            "adapter_id": "example-v1",
        },
    }


def test_worker_requires_audited_runnable_adapter():
    assert challenge_execution_allowed(base_challenge()) is True


def test_worker_rejects_research_mode():
    record = base_challenge()
    record["verification"]["execution_mode"] = "RESEARCH"
    assert challenge_execution_allowed(record) is False


def test_worker_rejects_unaudited_adapter():
    record = base_challenge()
    record["verification"]["adapter_audited"] = False
    assert challenge_execution_allowed(record) is False


def test_worker_rejects_non_runnable_adapter():
    record = base_challenge()
    record["verification"]["adapter_runnable"] = False
    assert challenge_execution_allowed(record) is False


def test_worker_rejects_unfunded_challenge():
    record = base_challenge()
    record["status"] = "OPEN + UNFUNDED"
    assert challenge_execution_allowed(record) is False
