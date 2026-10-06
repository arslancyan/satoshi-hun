from pathlib import Path


def test_protocol_migration_declares_core_tables():
    sql=(Path("backend/migrations/004_protocol_v1.sql")).read_text()
    for table in (
        "worker_capabilities","job_checkpoints","work_proofs",
        "reputation_events","challenge_creators","challenge_offers",
        "scheduler_decisions","security_events",
    ):
        assert f"create table if not exists {table}" in sql


def test_schema_keeps_non_custodial_boundary():
    sql=Path("backend/schema.sql").read_text()
    assert "private key" in sql.lower() or "seed phrases" in sql.lower()

def test_worker_idempotency_table_follows_workers_table():
    sql=Path("backend/schema.sql").read_text()
    assert sql.index("create table if not exists workers") < sql.index("create table if not exists worker_idempotency_records")


def test_reward_event_keeps_claim_provenance():
    sql=Path("backend/schema.sql").read_text()
    assert "source_claim_id uuid references work_claims(id)" in sql
    assert "uq_reward_event_claim" in sql


def test_api_claim_verification_contract():
    api=Path("backend/api.py").read_text()
    claims=api[api.index('@app.post("/jobs/{job_id}/claims")'):]
    verify=api[api.index('@app.post("/jobs/{job_id}/verify")'):]
    assert 'body.result_status == "VERIFIED"' in claims
    assert "server-side challenge adapter" in claims
    assert "c.result_status='TESTED'" in verify
    assert "source_claim_id" in verify
    assert "'REVIEW',%s" in verify


def test_api_assignment_economic_guard_contract():
    api=Path("backend/api.py").read_text()
    section=api[api.index('@app.post("/jobs/{job_id}/assign")'):]
    assert "economic_capacity(cur, job_id)" in section
    assert 'if not capacity["allowed"]' in section
    assert "Allocation paused:" in section


def test_api_worker_mutation_idempotency_contract():
    api=Path("backend/api.py").read_text()
    for marker in (
        '@app.post("/assignments/{assignment_id}/start")',
        '@app.post("/assignments/{assignment_id}/heartbeat")',
        '@app.post("/assignments/{assignment_id}/complete")',
        '@app.post("/jobs/{job_id}/claims")',
    ):
        section=api[api.index(marker):]
        assert "worker_idempotency_replay" in section
        assert "worker_idempotency_store" in section
