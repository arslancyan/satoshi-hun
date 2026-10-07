from beta_policy import BetaPolicy, beta_worker_eligible, runnable_challenge_ids


def test_beta_is_fail_closed_when_disabled():
    ok, reasons = beta_worker_eligible(
        policy=BetaPolicy(enabled=False), worker_status="ACTIVE",
        account_status="ACTIVE", challenge_runnable=True, active_worker_count=0)
    assert not ok
    assert "beta_disabled" in reasons


def test_beta_requires_runnable_challenge_and_capacity():
    policy = BetaPolicy(enabled=True, max_active_workers=2)
    ok, reasons = beta_worker_eligible(
        policy=policy, worker_status="ACTIVE", account_status="ACTIVE",
        challenge_runnable=False, active_worker_count=2)
    assert not ok
    assert "challenge_not_runnable" in reasons
    assert "beta_capacity_reached" in reasons


def test_beta_accepts_eligible_worker():
    ok, reasons = beta_worker_eligible(
        policy=BetaPolicy(enabled=True, max_active_workers=2),
        worker_status="ACTIVE", account_status="ACTIVE",
        challenge_runnable=True, active_worker_count=1)
    assert ok
    assert reasons == []


def test_runnable_catalog_never_infers_from_funding_only():
    challenges = [
        {"id": "funded-research", "funded": True, "runnable": False},
        {"id": "real-runnable", "funded": True, "runnable": True},
        {"id": "missing-flag", "funded": True},
    ]
    assert runnable_challenge_ids(challenges) == ["real-runnable"]
