
-- Economic safety: bound concurrent allocation and make worker-hour ceilings
-- explicit in deployment configuration. These are server-side guards only;
-- worker compute remains local and opt-in.
-- MAX_ACTIVE_ASSIGNMENTS defaults to 100.
-- MAX_ACTIVE_ASSIGNMENTS_PER_JOB defaults to 1.
-- MAX_NETWORK_WORKER_HOURS_PER_DAY defaults to 10000.


-- Concurrency invariant: a public challenge has exactly one coordination job.
-- This closes the check-then-insert race during concurrent challenge ingestion.
create unique index if not exists uq_public_challenge_job
  on jobs(puzzle_id,scope);
