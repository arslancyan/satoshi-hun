-- Persist public challenge search telemetry used by marketplace ranking.
-- No private keys, seed phrases, or signing material are stored.

alter table challenge_registry
  add column if not exists search_metrics jsonb not null default '{}'::jsonb;

alter table challenge_registry
  add column if not exists expected_value_score numeric(30,12) not null default 0;

create index if not exists idx_challenge_registry_expected_value
  on challenge_registry(expected_value_score desc, updated_at desc);

create table if not exists challenge_metric_snapshots (
  id uuid primary key,
  challenge_id text not null references challenge_registry(id) on delete cascade,
  metrics jsonb not null,
  captured_at timestamptz not null default now()
);

create index if not exists idx_challenge_metric_snapshots_challenge
  on challenge_metric_snapshots(challenge_id,captured_at desc);

create index if not exists idx_challenge_registry_search_metrics
  on challenge_registry using gin(search_metrics);
