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

-- Per-worker authentication token (hash only).
alter table workers add column if not exists token_hash text;
create unique index if not exists uq_workers_token_hash on workers(token_hash) where token_hash is not null;


-- Tamper-evident audit event ledger.
create table if not exists audit_events (
  id uuid primary key,
  event_type text not null,
  entity_type text not null,
  entity_id text not null,
  account_id uuid references accounts(id) on delete set null,
  worker_id uuid references workers(id) on delete set null,
  payload jsonb not null default '{}'::jsonb,
  previous_hash text,
  event_hash text not null unique,
  created_at timestamptz not null default now()
);
create index if not exists idx_audit_events_entity on audit_events(entity_type,entity_id,created_at);
create index if not exists idx_audit_events_account on audit_events(account_id,created_at);
