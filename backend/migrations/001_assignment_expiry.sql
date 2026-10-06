-- Satoshi Hunt migration 001: assignment expiry + stale-work protection
-- Review before applying to an existing production database.

alter table job_assignments drop constraint if exists job_assignments_status_check;
alter table job_assignments add constraint job_assignments_status_check
  check (status in ('ASSIGNED','RUNNING','COMPLETED','RELEASED','EXPIRED'));

alter table job_assignments add column if not exists expired_at timestamptz;
create index if not exists idx_assignments_stale on job_assignments(status,last_heartbeat_at);

-- Keep reward accounting explicitly non-custodial and review-gated.
alter table reward_events drop constraint if exists reward_events_settlement_status_check;
alter table reward_events add constraint reward_events_settlement_status_check
  check (settlement_status in ('REVIEW','APPROVED','SETTLED','VOID'));
