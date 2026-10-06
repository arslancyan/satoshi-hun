from pathlib import Path
SQL=Path("backend/schema.sql").read_text()
API=Path("backend/api.py").read_text()

def test_database_enforces_one_active_assignment_per_job():
    assert "uq_active_job_assignment" in SQL
    assert "where status in ('ASSIGNED','RUNNING')" in SQL

def test_assignment_path_serializes_capacity_decisions():
    helper=API[API.index("def economic_capacity"):API.index('@app.post("/jobs/{job_id}/assign")')]
    assert "pg_advisory_xact_lock(93218471)" in helper
    assert "MAX_ACTIVE_ASSIGNMENTS" in helper
    assert "MAX_ACTIVE_ASSIGNMENTS_PER_JOB" in helper

def test_assignment_path_checks_capacity_before_insert():
    section=API[API.index('@app.post("/jobs/{job_id}/assign")'):]
    assert "economic_capacity(cur, job_id)" in section
    assert "insert into job_assignments" in section

def test_claim_uniqueness_is_database_enforced():
    assert "unique (job_id, candidate_hash)" in SQL

def test_database_enforces_one_public_job_per_puzzle():
    assert "uq_public_challenge_job" in SQL
    assert "on jobs(puzzle_id,scope)" in SQL

def test_ingestion_handles_concurrent_job_creation():
    section=API[API.index('@app.post("/internal/challenges")'):API.index('@app.get("/admin/rewards")')]
    assert "on conflict (puzzle_id,scope) do nothing returning id" in section
    assert "select id from jobs where puzzle_id=%s and scope='public-reward-challenge' " in section


def test_checkpoint_cursor_is_monotonic():
    section=API[API.index('@app.post("/assignments/{assignment_id}/checkpoint")'):API.index('@app.post("/assignments/{assignment_id}/resume")')]
    assert "Checkpoint cursor must advance monotonically" in section
    assert "Checkpoint range changed for this assignment" in section
    assert "order by created_at desc,id desc limit 1 for update" in section

def test_resume_requires_active_assignment():
    section=API[API.index('@app.post("/assignments/{assignment_id}/resume")'):API.index('@app.get("/audit/explorer")')]
    assert 'row[1] not in ("ASSIGNED","RUNNING")' in section
    assert "Assignment is no longer resumable" in section


def test_completion_splits_worker_hours_across_utc_days():
    section=API[API.index('@app.post("/assignments/{assignment_id}/complete")'):API.index('@app.post("/jobs/{job_id}/claims")')]
    assert "period_start=started_at.date()" in section
    assert "while period_start <= end_date:" in section
    assert "seconds_verified" in section


def test_claim_compute_time_is_server_bounded():
    section=API[API.index('@app.post("/jobs/{job_id}/claims")'):API.index('@app.get("/audit/job/{job_id}")')]
    assert "elapsed_seconds=max(0,int((datetime.now(timezone.utc)-started_at).total_seconds()))" in section
    assert "server_cpu_ceiling=min(86400, elapsed_seconds*cpu_threads)" in section
    assert "accepted_cpu_seconds=min(body.cpu_seconds, server_cpu_ceiling)" in section


def test_duplicate_claim_uses_savepoint_not_full_transaction_rollback():
    section=API[API.index('@app.post("/jobs/{job_id}/claims")'):API.index('@app.get("/audit/job/{job_id}")')]
    assert "with conn.transaction():" in section
    assert "conn.rollback()" not in section
    assert "worker_idempotency_store(cur, token_worker_id, request, payload, response)" in section


def test_stale_assignment_recovery_is_audited():
    section=API[API.index("def expire_stale_assignments"):API.index("def assignment_for_worker")]
    assert "returning id,job_id,worker_id" in section
    assert '"EXPIRED"' in section
    assert '"timeout_seconds":ASSIGNMENT_TIMEOUT_SECONDS' in section


def test_worker_revoke_requeues_active_assignments():
    section=API[API.index('@app.post("/workers/{worker_id}/revoke")'):API.index('@app.get("/workers")')]
    assert "status='EXPIRED'" in section
    assert "returning id,job_id" in section
    assert "status='QUEUED'" in section
    assert 'reason":"worker_revoked' in section
