-- Independent on-chain funding verification fields.
alter table challenge_registry add column if not exists advertised_reward_btc numeric(20,8);
alter table challenge_registry add column if not exists verified_balance_btc numeric(20,8);
alter table challenge_registry add column if not exists funding_match boolean not null default false;
alter table challenge_registry add column if not exists verification_stale boolean not null default true;
alter table challenge_registry add column if not exists last_live_check_error text;
create index if not exists idx_challenge_registry_funding_match on challenge_registry(status,funding_match,verification_stale,balance_btc);
