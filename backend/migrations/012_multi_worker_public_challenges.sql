-- Allow multiple workers to work on the same unresolved public challenge.
-- Keep one active assignment per worker per job so repeat clicks are idempotent.
drop index if exists uq_active_job_assignment;
create unique index if not exists uq_active_job_worker_assignment
  on job_assignments(job_id, worker_id)
  where status in ('ASSIGNED','RUNNING');
create index if not exists idx_active_job_assignments
  on job_assignments(job_id, status)
  where status in ('ASSIGNED','RUNNING');
