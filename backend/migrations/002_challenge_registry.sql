-- Satoshi Hunt migration 002: server-side challenge registry + reward uniqueness

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

create unique index if not exists uq_reward_event_puzzle_account
  on reward_events(puzzle_id,account_id) where settlement_status <> 'VOID';
