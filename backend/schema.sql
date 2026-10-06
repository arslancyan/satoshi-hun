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

create table if not exists idempotency_keys (
  account_id uuid not null references accounts(id) on delete cascade,
  idempotency_key text not null,
  response_json jsonb not null,
  created_at timestamptz not null default now(),
  primary key (account_id, idempotency_key)
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

create table if not exists worker_idempotency_records (
  worker_id uuid not null references workers(id) on delete cascade,
  idempotency_key text not null,
  request_hash text not null,
  response_json jsonb not null,
  created_at timestamptz not null default now(),
  primary key (worker_id, idempotency_key)
);
create index if not exists idx_worker_idempotency_records_created_at on worker_idempotency_records(created_at);

create table if not exists challenge_registry (
  id text primary key,
  title text not null,
  challenge_type text not null,
  reward_btc numeric(20,8) not null check (reward_btc > 0),
  balance_btc numeric(20,8) not null check (balance_btc >= 0),
  status text not null check (status in ('OPEN + FUNDED','OPEN + UNFUNDED','SOLVED + FUNDED','SOLVED + EMPTY','UNKNOWN')),
  rules text not null,
  provenance jsonb not null,
  verification jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_challenge_registry_status on challenge_registry(status);

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
  source_claim_id uuid references work_claims(id),
  approved_at timestamptz,
  settled_at timestamptz,
  check (worker_share_btc + platform_fee_btc = gross_reward_btc)
);

create table if not exists community_allocations (
  id uuid primary key,
  source_reward_event_id uuid references reward_events(id),
  amount_btc numeric(20,8) not null check (amount_btc > 0),
  status text not null default 'MANUAL_REVIEW'
    check (status in ('MANUAL_REVIEW','APPROVED','DISTRIBUTED','CANCELLED')),
  created_at timestamptz not null default now(),
  approved_at timestamptz,
  distributed_at timestamptz
);

create index if not exists idx_workers_account on workers(account_id);
create index if not exists idx_jobs_puzzle on jobs(puzzle_id);
create unique index if not exists uq_public_challenge_job
  on jobs(puzzle_id,scope);
create index if not exists idx_claims_worker on work_claims(worker_id);
create index if not exists idx_reward_events_account on reward_events(account_id);
create unique index if not exists uq_reward_event_puzzle_account on reward_events(puzzle_id,account_id) where settlement_status <> 'VOID';
create unique index if not exists uq_reward_event_claim on reward_events(source_claim_id) where source_claim_id is not null;


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


create table if not exists idempotency_records (
  account_id uuid not null references accounts(id) on delete cascade,
  idempotency_key text not null,
  request_hash text not null,
  response_json jsonb not null,
  created_at timestamptz not null default now(),
  primary key (account_id, idempotency_key)
);
create index if not exists idx_idempotency_records_created_at on idempotency_records(created_at);

-- Checkpoint history remains append-only; the API enforces monotonic cursor advancement.

 
-- Non-custodial reward ledger. Balances are accounting claims only; Satoshi Hunt
-- never stores private keys or signs/broadcasts Bitcoin transactions.
create table if not exists reward_balances (
  account_id uuid primary key references accounts(id) on delete cascade,
  available_btc numeric(20,8) not null default 0 check (available_btc >= 0),
  updated_at timestamptz not null default now()
);

create table if not exists reward_ledger (
  id uuid primary key,
  account_id uuid not null references accounts(id) on delete cascade,
  reward_event_id uuid not null references reward_events(id),
  entry_type text not null check (entry_type in ('WORKER_CREDIT','PLATFORM_FEE')),
  amount_btc numeric(20,8) not null check (amount_btc > 0),
  created_at timestamptz not null default now()
);

create unique index if not exists uq_reward_ledger_event_type
  on reward_ledger(reward_event_id,entry_type);

create table if not exists withdrawal_requests (
  id uuid primary key,
  account_id uuid not null references accounts(id) on delete cascade,
  amount_btc numeric(20,8) not null check (amount_btc > 0),
  payout_address text not null,
  status text not null default 'QUEUED'
    check (status in ('QUEUED','PROCESSING','PAID','FAILED','CANCELLED')),
  external_reference text,
  created_at timestamptz not null default now(),
  processed_at timestamptz
);

create index if not exists idx_withdrawals_account on withdrawal_requests(account_id,created_at);

-- Account passwords are salted PBKDF2 hashes; plaintext passwords are never stored.
alter table accounts add column if not exists password_hash text;
create index if not exists idx_withdrawals_status_created on withdrawal_requests(status,created_at);
