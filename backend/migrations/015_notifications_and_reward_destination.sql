-- Satoshi Hunt notification + reward destination hardening
-- Notifications are account-scoped and contain no secrets.
create table if not exists notifications (
  id uuid primary key,
  account_id uuid not null references accounts(id) on delete cascade,
  event_type text not null,
  title text not null,
  message text not null,
  metadata jsonb not null default '{}'::jsonb,
  read_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists idx_notifications_account_created
  on notifications(account_id, created_at desc);
create index if not exists idx_notifications_account_unread
  on notifications(account_id, read_at);

alter table reward_ledger
  add column if not exists destination_btc_address text;
