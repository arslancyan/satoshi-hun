from pathlib import Path
import os

p=Path(os.environ.get("SATOSHI_HUNT_API_PATH", "/app/backend/api.py"))
s=p.read_text()

old='''            cur.execute("select id from job_assignments where job_id=%s and status in ('ASSIGNED','RUNNING')",(job_id,))
            if cur.fetchone(): raise HTTPException(409,"Challenge is already being run by another worker")
            # Account-level exclusivity: switching puzzles pauses the account's
            # previous active assignment, even when it uses another worker.
            cur.execute(
                "update job_assignments set status='PAUSED',completed_at=null "
                "where worker_id in (select id from workers where account_id=%s) "
                "and status in ('ASSIGNED','RUNNING') "
                "returning id,job_id,worker_id",
                (account_id,),
            )
            paused_assignments=cur.fetchall()
            for paused_id, paused_job_id, paused_worker_id in paused_assignments:
                cur.execute(
                    "update jobs set status='QUEUED',completed_at=null "
                    "where id=%s and status='RUNNING'",
                    (paused_job_id,),
                )
            capacity=economic_capacity(cur,job_id)'''
new='''            cur.execute("select id,status from job_assignments where job_id=%s and worker_id=%s and status in ('ASSIGNED','RUNNING')",(job_id,body.worker_id))
            existing_assignment=cur.fetchone()
            if existing_assignment:
                response={"challenge_id":challenge_id,"job_id":str(job_id),"assignment_id":str(existing_assignment[0]),"worker_id":str(body.worker_id),"status":existing_assignment[1]}
                idempotency_store(cur,account_id,request,payload,response)
                return response
            capacity=economic_capacity(cur,job_id)'''
if old in s:
    s=s.replace(old,new,1)

old2='''    cur.execute(
        "update jobs set status='VERIFIED',completed_at=coalesce(completed_at,now()) where id=%s",
        (job_id,),
    )'''
new2='''    cur.execute(
        "update jobs set status='VERIFIED',completed_at=coalesce(completed_at,now()) where id=%s",
        (job_id,),
    )
    cur.execute(
        "update job_assignments set status='COMPLETED',completed_at=now(),last_heartbeat_at=null "
        "where id=(select id from job_assignments where job_id=%s and worker_id=%s and status='RUNNING' order by assigned_at desc limit 1)",
        (job_id,worker_id),
    )
    cur.execute(
        "update job_assignments set status='RELEASED',completed_at=now(),last_heartbeat_at=null "
        "where job_id=%s and status in ('ASSIGNED','RUNNING')",
        (job_id,),
    )'''
if old2 not in s:
    raise SystemExit("reward patch target not found")
s=s.replace(old2,new2,1)
# Serialize concurrent marketplace puzzle switches per account.
_run_marker='@app.post("/marketplace/challenges/{challenge_id}/run")'
if _run_marker in s:
    _run_start=s.index(_run_marker)
    _run_tail=s[_run_start:]
    _run_needle='            if replay is not None: return replay'
    _run_insert=_run_needle+'\n            cur.execute("select pg_advisory_xact_lock(hashtext(%s))",(str(account_id),))\n            # One active puzzle per account: serialize concurrent switches.'
    if _run_needle in _run_tail and "pg_advisory_xact_lock(hashtext(%s))" not in _run_tail:
        _run_tail=_run_tail.replace(_run_needle,_run_insert,1)
        s=s[:_run_start]+_run_tail
p.write_text(s)


# Ensure paused-assignment schema exists on existing production databases.
import psycopg
from os import environ
_db=environ.get("DATABASE_URL","")
if _db:
    with psycopg.connect(_db) as conn:
        with conn.cursor() as cur:
            cur.execute("alter table job_assignments drop constraint if exists job_assignments_status_check")
            cur.execute("alter table job_assignments add constraint job_assignments_status_check check (status in ('ASSIGNED','RUNNING','PAUSED','COMPLETED','RELEASED','EXPIRED'))")
            cur.execute("create index if not exists idx_assignments_paused on job_assignments(worker_id,status,assigned_at desc) where status='PAUSED'")


# Central BTC Treasury schema/bootstrap. This keeps existing Railway databases
# compatible while migrations are applied through normal deployment history.
if _db:
    with psycopg.connect(_db) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                create table if not exists treasury_wallets (
                  id uuid primary key,
                  label text not null unique,
                  network text not null check (network in ('bitcoin-mainnet','bitcoin-testnet')),
                  address text not null unique,
                  status text not null default 'ACTIVE' check (status in ('ACTIVE','PAUSED','DISABLED')),
                  created_at timestamptz not null default now()
                )
            """)
            cur.execute("""
                create table if not exists treasury_accounting (
                  id uuid primary key references treasury_wallets(id) on delete cascade,
                  funded_btc numeric(20,8) not null default 0 check (funded_btc >= 0),
                  reserved_btc numeric(20,8) not null default 0 check (reserved_btc >= 0),
                  solver_liability_btc numeric(20,8) not null default 0 check (solver_liability_btc >= 0),
                  owner_liability_btc numeric(20,8) not null default 0 check (owner_liability_btc >= 0),
                  updated_at timestamptz not null default now(),
                  check (funded_btc >= reserved_btc)
                )
            """)
            cur.execute("""
                create table if not exists treasury_funding (
                  id uuid primary key,
                  wallet_id uuid not null references treasury_wallets(id),
                  amount_btc numeric(20,8) not null check (amount_btc > 0),
                  external_txid text not null unique,
                  status text not null default 'CONFIRMED' check (status in ('PENDING','CONFIRMED','REVERSED')),
                  created_at timestamptz not null default now()
                )
            """)
            cur.execute("""
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
                )
            """)
            cur.execute("create index if not exists idx_treasury_ledger_created on treasury_ledger(wallet_id,created_at desc)")
            cur.execute("create index if not exists idx_treasury_ledger_reference on treasury_ledger(reference_type,reference_id)")
            cur.execute("""
                insert into treasury_wallets(id,label,network,address,status)
                values(
                  '00000000-0000-0000-0000-000000000001',
                  'Satoshi Hunt BTC Treasury',
                  'bitcoin-mainnet',
                  'bc1ptstlyntypqqf8s5qz3jwcsrxw2pxqj634c7pklj2mjlvqwl22l6qqq8csl',
                  'ACTIVE'
                )
                on conflict (id) do update set address=excluded.address,network=excluded.network,status=excluded.status
            """)
            cur.execute("""
                insert into treasury_accounting(id)
                values('00000000-0000-0000-0000-000000000001')
                on conflict (id) do nothing
            """)


# Secure PSBT payout settlement bootstrap.
if _db:
    with psycopg.connect(_db) as conn:
        with conn.cursor() as cur:
            cur.execute("""
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
                )
            """)
            cur.execute("alter table payout_settlements add column if not exists signed_psbt text")
            cur.execute("alter table payout_settlements add column if not exists signed_tx_hex text")
            cur.execute("alter table payout_settlements add column if not exists payout_digest text")
            cur.execute("alter table withdrawal_requests add column if not exists settlement_id uuid references payout_settlements(id)")
            cur.execute("""
                create table if not exists payout_settlement_events (
                  id uuid primary key,
                  settlement_id uuid not null references payout_settlements(id) on delete cascade,
                  event_type text not null,
                  signer_id text,
                  txid text,
                  metadata jsonb not null default '{}'::jsonb,
                  created_at timestamptz not null default now()
                )
            """)
            cur.execute("create index if not exists idx_payout_settlements_status on payout_settlements(status,created_at)")
            cur.execute("create index if not exists idx_payout_settlement_events on payout_settlement_events(settlement_id,created_at)")
