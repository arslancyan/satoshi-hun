-- Allow a user to switch puzzles without losing the previous assignment.
alter table job_assignments drop constraint if exists job_assignments_status_check;
alter table job_assignments add constraint job_assignments_status_check
  check (status in ('ASSIGNED','RUNNING','PAUSED','COMPLETED','RELEASED','EXPIRED'));

create index if not exists idx_assignments_paused
  on job_assignments(worker_id,status,assigned_at desc)
  where status='PAUSED';
