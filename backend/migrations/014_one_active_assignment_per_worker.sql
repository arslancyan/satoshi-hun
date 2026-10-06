-- Prevent one worker from consuming multiple public puzzle assignments at once.
-- Historical PAUSED/COMPLETED/EXPIRED assignments remain allowed.
create unique index if not exists uq_active_worker_assignment
  on job_assignments(worker_id)
  where status in ('ASSIGNED','RUNNING');
