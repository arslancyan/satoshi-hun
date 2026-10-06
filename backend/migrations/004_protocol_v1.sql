-- Satoshi Hunt Protocol v1: scheduling, proof, recovery, reputation, creator marketplace.

create table if not exists worker_capabilities (
  worker_id uuid primary key references workers(id) on delete cascade,
  cpu_threads integer not null default 1 check (cpu_threads > 0 and cpu_threads <= 1024),
  memory_mb integer not null default 512 check (memory_mb > 0),
  adapter_types jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists job_checkpoints (
  id uuid primary key,
  job_id uuid not null references jobs(id) on delete cascade,
  assignment_id uuid not null references job_assignments(id) on delete cascade,
  cursor_start bigint not null check (cursor_start >= 0),
  cursor_end bigint not null check (cursor_end > cursor_start),
  cursor_next bigint not null check (cursor_next >= cursor_start and cursor_next <= cursor_end),
  checkpoint_hash text not null,
  created_at timestamptz not null default now()
);
create index if not exists idx_checkpoints_job on job_checkpoints(job_id,created_at desc);

create table if not exists work_proofs (
  id uuid primary key,
  assignment_id uuid not null references job_assignments(id) on delete cascade,
  worker_id uuid not null references workers(id) on delete cascade,
  proof_type text not null check (proof_type in ('CHECKPOINT','COMPLETION','VERIFICATION')),
  proof_hash text not null,
  nonce text,
  cpu_seconds integer not null default 0 check (cpu_seconds >= 0),
  created_at timestamptz not null default now(),
  unique(assignment_id,proof_type,proof_hash)
);
create index if not exists idx_work_proofs_worker on work_proofs(worker_id,created_at desc);

create table if not exists reputation_events (
  id uuid primary key,
  account_id uuid references accounts(id) on delete cascade,
  worker_id uuid references workers(id) on delete cascade,
  event_type text not null,
  weight numeric(12,4) not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists challenge_creators (
  challenge_id text primary key references challenge_registry(id) on delete cascade,
  creator_account_id uuid references accounts(id) on delete set null,
  terms jsonb not null default '{}'::jsonb,
  creator_status text not null default 'PENDING'
    check (creator_status in ('PENDING','APPROVED','SUSPENDED','REJECTED')),
  created_at timestamptz not null default now(),
  approved_at timestamptz
);

create table if not exists challenge_offers (
  id uuid primary key,
  challenge_id text not null references challenge_registry(id) on delete cascade,
  creator_account_id uuid references accounts(id) on delete set null,
  reward_btc numeric(20,8) not null check (reward_btc > 0),
  estimated_difficulty numeric(12,4),
  estimated_seconds bigint check (estimated_seconds is null or estimated_seconds >= 0),
  required_capabilities jsonb not null default '{}'::jsonb,
  status text not null default 'DRAFT'
    check (status in ('DRAFT','PUBLISHED','PAUSED','CLOSED')),
  created_at timestamptz not null default now(),
  published_at timestamptz
);
create index if not exists idx_challenge_offers_status on challenge_offers(status);

create table if not exists scheduler_decisions (
  id uuid primary key,
  job_id uuid not null references jobs(id) on delete cascade,
  worker_id uuid references workers(id) on delete set null,
  score numeric(14,6) not null,
  reason jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_scheduler_job on scheduler_decisions(job_id,created_at desc);

create table if not exists security_events (
  id uuid primary key,
  account_id uuid references accounts(id) on delete set null,
  worker_id uuid references workers(id) on delete set null,
  event_type text not null,
  severity text not null check (severity in ('INFO','WARN','HIGH')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_security_events_created on security_events(created_at desc);
