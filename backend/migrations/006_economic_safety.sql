
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

 
-- Non-custodial reward balance/withdrawal accounting.
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
