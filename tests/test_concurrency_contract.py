[object Object]

def test_database_enforces_one_public_job_per_puzzle():
    assert "uq_public_challenge_job" in SQL
    assert "on jobs(puzzle_id,scope)" in SQL

def test_ingestion_handles_concurrent_job_creation():
    section=API[API.index('@app.post("/internal/challenges")'):API.index('@app.get("/admin/rewards")')]
    assert "on conflict (puzzle_id,scope) do nothing returning id" in section
    assert "select id from jobs where puzzle_id=%s and scope='public-reward-challenge' " in section
