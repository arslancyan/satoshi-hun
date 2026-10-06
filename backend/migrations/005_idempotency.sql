-- Production hardening: durable idempotency records for authenticated account mutations.
-- Replays return the original response and never execute the mutation again.
create table if not exists idempotency_records (
  account_id uuid not null references accounts(id) on delete cascade,
  idempotency_key text not null,
  request_hash text not null,
  response_json jsonb not null,
  created_at timestamptz not null default now(),
  primary key (account_id, idempotency_key)
);
create index if not exists idx_idempotency_records_created_at on idempotency_records(created_at);
