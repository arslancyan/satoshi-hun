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
