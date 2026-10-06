alter table challenge_registry add column if not exists funding_snapshot jsonb not null default '{}'::jsonb;
alter table challenge_registry add column if not exists solve_evidence jsonb not null default '{}'::jsonb;
create index if not exists idx_challenge_registry_live_verification on challenge_registry(source_adapter,verification_stale);
