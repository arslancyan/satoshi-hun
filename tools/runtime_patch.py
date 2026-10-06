from pathlib import Path

p=Path("/app/backend/api.py")
s=p.read_text()

old='''            cur.execute("select id from job_assignments where job_id=%s and status in ('ASSIGNED','RUNNING')",(job_id,))
            if cur.fetchone(): raise HTTPException(409,"Challenge is already being run by another worker")
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
