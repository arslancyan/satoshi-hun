-- Operational hardening: idempotency and worker token rotation.

create table if not exists idempotency_keys (
  account_id uuid not null references accounts(id) on delete cascade,
  idempotency_key text not null,
  response_json jsonb not null,
  created_at timestamptz not null default now(),
  primary key (account_id, idempotency_key)
);

create index if not exists idx_idempotency_created_at on idempotency_keys(created_at);
