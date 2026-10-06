-- Central BTC Treasury accounting and withdrawal reservation.
-- Public wallet metadata only; never store private keys or signing credentials.

create table if not exists treasury_wallets (
  id uuid primary key,
  label text not null unique,
  network text not null check (network in ('bitcoin-mainnet','bitcoin-testnet')),
  address text not null unique,
  status text not null default 'ACTIVE' check (status in ('ACTIVE','PAUSED','DISABLED')),
  created_at timestamptz not null default now()
);

create table if not exists treasury_accounting (
  id uuid primary key references treasury_wallets(id) on delete cascade,
  funded_btc numeric(20,8) not null default 0 check (funded_btc >= 0),
  reserved_btc numeric(20,8) not null default 0 check (reserved_btc >= 0),
  solver_liability_btc numeric(20,8) not null default 0 check (solver_liability_btc >= 0),
  owner_liability_btc numeric(20,8) not null default 0 check (owner_liability_btc >= 0),
  updated_at timestamptz not null default now(),
  check (funded_btc >= reserved_btc)
);

create table if not exists treasury_funding (
  id uuid primary key,
  wallet_id uuid not null references treasury_wallets(id),
  amount_btc numeric(20,8) not null check (amount_btc > 0),
  external_txid text not null unique,
  status text not null default 'CONFIRMED' check (status in ('PENDING','CONFIRMED','REVERSED')),
  created_at timestamptz not null default now()
);

create table if not exists treasury_ledger (
  id uuid primary key,
  wallet_id uuid not null references treasury_wallets(id),
  entry_type text not null check (entry_type in (
    'FUNDING_CREDIT','REWARD_LIABILITY','OWNER_LIABILITY',
    'USER_WITHDRAWAL_RESERVED','USER_WITHDRAWAL_SETTLED','OWNER_PAYOUT_SETTLED'
  )),
  amount_btc numeric(20,8) not null check (amount_btc > 0),
  reference_type text not null,
  reference_id text,
  account_id uuid references accounts(id) on delete set null,
  destination_btc_address text,
  created_at timestamptz not null default now()
);

create index if not exists idx_treasury_ledger_created on treasury_ledger(wallet_id,created_at desc);
create index if not exists idx_treasury_ledger_reference on treasury_ledger(reference_type,reference_id);

insert into treasury_wallets(id,label,network,address,status)
values(
  '00000000-0000-0000-0000-000000000001',
  'Satoshi Hunt BTC Treasury',
  'bitcoin-mainnet',
  'bc1ptstlyntypqqf8s5qz3jwcsrxw2pxqj634c7pklj2mjlvqwl22l6qqq8csl',
  'ACTIVE'
)
on conflict (id) do update set address=excluded.address, network=excluded.network, status=excluded.status;

insert into treasury_accounting(id)
values('00000000-0000-0000-0000-000000000001')
on conflict (id) do nothing;
