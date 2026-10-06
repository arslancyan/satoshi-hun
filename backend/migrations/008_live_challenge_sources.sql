alter table challenge_registry add column if not exists payout jsonb not null default '{}'::jsonb;
alter table challenge_registry add column if not exists source_adapter text;
alter table challenge_registry add column if not exists live_checked_at timestamptz;
alter table challenge_registry add column if not exists live_verification jsonb not null default '{}'::jsonb;
create index if not exists idx_challenge_registry_live on challenge_registry(status,balance_btc,live_checked_at);
create table if not exists challenge_selections (account_id uuid not null references accounts(id) on delete cascade, challenge_id text not null references challenge_registry(id) on delete cascade, selected_at timestamptz not null default now(), primary key(account_id,challenge_id));
create index if not exists idx_challenge_selections_account on challenge_selections(account_id,selected_at desc);
