-- Satoshi Hunt backend foundation (non-custodial)
-- Stores attribution/accounting metadata only. Never store private keys or seed phrases.

create table if not exists auth_links (
  email text primary key,
  token_hash text not null,
  expires_at timestamptz not null
);

create table if not exists accounts (
  id uuid primary key,
  email text not null unique,
  btc_payout_address text,
  created_at timestamptz not null default now()
);

create table if not exists workers (
  id uuid primary key,
  account_id uuid not null references accounts(id) on delete cascade,
  label text not null default 'worker',
  status text not null default 'ACTIVE'
    check (status in ('ACTIVE','PAUSED','REVOKED')),
  registered_at timestamptz not null default now(),
  last_seen_at timestamptz,
  token_hash text unique
);

create table if not exists jobs (
  id uuid primary key,
  puzzle_id text not null,
  scope text not null check (scope = 'public-reward-challenge'),
  status text not null default 'QUEUED'
    check (status in ('QUEUED','RUNNING','COMPLETED','VERIFIED','REJECTED','EXPIRED')),
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

-- Immutable assignment history: a job can move through workers without
-- losing attribution. Only server timestamps count toward verified hours.
create table if not exists job_assignments (
  id uuid primary key,
  job_id uuid not null references jobs(id) on delete cascade,
  worker_id uuid not null references workers(id) on delete cascade,
  status text not null default 'ASSIGNED'
    check (status in ('ASSIGNED','RUNNING','COMPLETED','RELEASED','EXPIRED')),
  assigned_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  last_heartbeat_at timestamptz,
  verified_seconds bigint not null default 0 check (verified_seconds >= 0),
  expired_at timestamptz
);

create unique index if not exists uq_active_job_assignment
  on job_assignments(job_id)
  where status in ('ASSIGNED','RUNNING');

create index if not exists idx_assignments_worker on job_assignments(worker_id);
create index if not exists idx_assignments_job on job_assignments(job_id);
create index if not exists idx_assignments_stale on job_assignments(status,last_heartbeat_at);

create table if not exists work_claims (
  id uuid primary key,
  job_id uuid not null references jobs(id) on delete cascade,
  worker_id uuid not null references workers(id) on delete cascade,
  candidate_hash text not null,
  result_status text not null
    check (result_status in ('TESTED','DUPLICATE','VERIFIED','REJECTED')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  cpu_seconds integer not null default 0 check (cpu_seconds >= 0),
  unique (job_id, candidate_hash)
);

create table if not exists worker_hours (
  id uuid primary key,
  account_id uuid not null references accounts(id) on delete cascade,
  worker_id uuid not null references workers(id) on delete cascade,
  period_start date not null,
  seconds_verified bigint not null default 0 check (seconds_verified >= 0),
  unique (worker_id, period_start)
);

create table if not exists reward_events (
  id uuid primary key,
  account_id uuid not null references accounts(id),
  puzzle_id text not null,
  gross_reward_btc numeric(20,8) not null check (gross_reward_btc > 0),
  worker_share_btc numeric(20,8) not null check (worker_share_btc >= 0),
  platform_fee_btc numeric(20,8) not null check (platform_fee_btc >= 0),
  settlement_status text not null default 'REVIEW'
    check (settlement_status in ('REVIEW','APPROVED','SETTLED','VOID')),
  created_at timestamptz not null default now(),
  check (worker_share_btc + platform_fee_btc = gross_reward_btc)
);

create table if not exists community_allocations (
  id uuid primary key,
  source_reward_event_id uuid references reward_events(id),
  amount_btc numeric(20,8) not null check (amount_btc > 0),
  status text not null default 'MANUAL_REVIEW'
    check (status in ('MANUAL_REVIEW','APPROVED','DISTRIBUTED','CANCELLED')),
  created_at timestamptz not null default now(),
  approved_at timestamptz
);

create index if not exists idx_workers_account on workers(account_id);
create index if not exists idx_jobs_puzzle on jobs(puzzle_id);
create index if not exists idx_claims_worker on work_claims(worker_id);
create index if not exists idx_reward_events_account on reward_events(account_id);
