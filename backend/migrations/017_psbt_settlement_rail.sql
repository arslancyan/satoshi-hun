-- Secure PSBT payout settlement rail.
create table if not exists payout_settlements (
  id uuid primary key,
  withdrawal_id uuid not null unique references withdrawal_requests(id) on delete restrict,
  wallet_id uuid not null references treasury_wallets(id),
  status text not null default 'PSBT_REQUESTED'
    check (status in ('PSBT_REQUESTED','PSBT_READY','SIGNED','BROADCAST','SETTLED','FAILED','CANCELLED')),
  amount_btc numeric(20,8) not null check (amount_btc > 0),
  destination_btc_address text not null,
  unsigned_psbt text,
  signed_psbt text,
  signed_tx_hex text,
  txid text,
  signer_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  signed_at timestamptz,
  broadcast_at timestamptz,
  settled_at timestamptz
);
create index if not exists idx_payout_settlements_status
  on payout_settlements(status,created_at);

alter table withdrawal_requests
  add column if not exists settlement_id uuid references payout_settlements(id);

-- Signer/broadcaster attestations are append-only audit records.
create table if not exists payout_settlement_events (
  id uuid primary key,
  settlement_id uuid not null references payout_settlements(id) on delete cascade,
  event_type text not null,
  signer_id text,
  txid text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_payout_settlement_events
  on payout_settlement_events(settlement_id,created_at);
