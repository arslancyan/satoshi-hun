from pathlib import Path
import os
import psycopg
from os import environ
_db=environ.get("DATABASE_URL","")

p=Path(os.environ.get("SATOSHI_HUNT_API_PATH", "/app/backend/api.py"))
s=p.read_text()

old='''            # Account-level exclusivity: switching puzzles pauses all active
            # assignments owned by this account, across all of its workers.
            cur.execute(
                "update job_assignments set status='PAUSED',completed_at=null,last_heartbeat_at=null "
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
            # Keep a repeated click on the currently active worker/challenge idempotent.
            cur.execute(
                "select id,status from job_assignments where job_id=%s and worker_id=%s "
                "and status in ('ASSIGNED','RUNNING')",
                (job_id,body.worker_id),
            )
            existing_assignment=cur.fetchone()
            if existing_assignment:
                response={"challenge_id":challenge_id,"job_id":str(job_id),
                          "assignment_id":str(existing_assignment[0]),"worker_id":str(body.worker_id),
                          "status":existing_assignment[1]}
                idempotency_store(cur,account_id,request,payload,response)
                return response
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
if old2 in s:
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
# Worker ChatGPT control endpoints are injected into the runtime API as well as source.
if '@app.post("/assignments/{assignment_id}/pause")' not in s:
    worker_control_routes = r'''@app.post("/assignments/{assignment_id}/pause")
def pause_assignment(assignment_id: UUID, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload={"assignment_id":str(assignment_id),"action":"pause"}
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None: return replay
            cur.execute("select a.id,a.job_id,a.worker_id,a.status,j.puzzle_id from job_assignments a join workers w on w.id=a.worker_id join jobs j on j.id=a.job_id where a.id=%s and w.account_id=%s for update",(assignment_id,account_id))
            row=cur.fetchone()
            if not row: raise HTTPException(404,"Assignment not found")
            if row[3] not in ("ASSIGNED","RUNNING"): raise HTTPException(409,f"Assignment is {row[3]}")
            cur.execute("update job_assignments set status='PAUSED',completed_at=null,last_heartbeat_at=null where id=%s",(assignment_id,))
            cur.execute("update jobs set status='QUEUED',completed_at=null where id=%s and status in ('ASSIGNED','RUNNING','QUEUED')",(row[1],))
            record_audit_event(cur,"PAUSED","assignment",assignment_id,account_id,row[2],{"job_id":str(row[1]),"puzzle_id":row[4],"reason":"worker_control"})
            response={"assignment_id":str(assignment_id),"job_id":str(row[1]),"puzzle_id":row[4],"status":"PAUSED"}
            idempotency_store(cur,account_id,request,payload,response)
            return response

@app.post("/assignments/{assignment_id}/stop")
def stop_assignment(assignment_id: UUID, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload={"assignment_id":str(assignment_id),"action":"stop"}
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None: return replay
            cur.execute("select a.id,a.job_id,a.worker_id,a.status,j.puzzle_id from job_assignments a join workers w on w.id=a.worker_id join jobs j on j.id=a.job_id where a.id=%s and w.account_id=%s for update",(assignment_id,account_id))
            row=cur.fetchone()
            if not row: raise HTTPException(404,"Assignment not found")
            if row[3] not in ("ASSIGNED","RUNNING"): raise HTTPException(409,f"Assignment is {row[3]}")
            cur.execute("update job_assignments set status='RELEASED',completed_at=now(),last_heartbeat_at=null where id=%s",(assignment_id,))
            cur.execute("update jobs set status='QUEUED',completed_at=null where id=%s and status in ('ASSIGNED','RUNNING','QUEUED')",(row[1],))
            record_audit_event(cur,"RELEASED","assignment",assignment_id,account_id,row[2],{"job_id":str(row[1]),"puzzle_id":row[4],"reason":"worker_control"})
            response={"assignment_id":str(assignment_id),"job_id":str(row[1]),"puzzle_id":row[4],"status":"RELEASED"}
            idempotency_store(cur,account_id,request,payload,response)
            return response

'''
    if marker in s:
        s=s.replace(marker,worker_control_routes+marker,1)

p.write_text(s)


# Account notifications and owner live-worker monitor.
if _db:
    with psycopg.connect(_db) as conn:
        with conn.cursor() as cur:
            cur.execute("""create table if not exists account_notifications (
                id uuid primary key,
                account_id uuid not null references accounts(id) on delete cascade,
                title text not null,
                message text not null,
                read_at timestamptz,
                created_at timestamptz not null default now()
            )""")
            cur.execute("create index if not exists idx_account_notifications_account_created on account_notifications(account_id,created_at desc)")

# Live challenge registry compatibility migrations. Older Railway databases may
# predate the search/ranking columns now required by the marketplace.
if _db:
    with psycopg.connect(_db) as conn:
        with conn.cursor() as cur:
            cur.execute("alter table challenge_registry add column if not exists payout jsonb not null default '{}'::jsonb")
            cur.execute("alter table challenge_registry add column if not exists source_adapter text")
            cur.execute("alter table challenge_registry add column if not exists live_checked_at timestamptz")
            cur.execute("alter table challenge_registry add column if not exists live_verification jsonb not null default '{}'::jsonb")
            cur.execute("alter table challenge_registry add column if not exists advertised_reward_btc numeric(20,8)")
            cur.execute("alter table challenge_registry add column if not exists verified_balance_btc numeric(20,8)")
            cur.execute("alter table challenge_registry add column if not exists funding_match boolean not null default false")
            cur.execute("alter table challenge_registry add column if not exists verification_stale boolean not null default true")
            cur.execute("alter table challenge_registry add column if not exists last_live_check_error text")
            cur.execute("alter table challenge_registry add column if not exists funding_snapshot jsonb not null default '{}'::jsonb")
            cur.execute("alter table challenge_registry add column if not exists solve_evidence jsonb not null default '{}'::jsonb")
            cur.execute("alter table challenge_registry add column if not exists search_metrics jsonb not null default '{}'::jsonb")
            cur.execute("alter table challenge_registry add column if not exists expected_value_score numeric(30,12) not null default 0")
            cur.execute("create table if not exists challenge_metric_snapshots (id uuid primary key, challenge_id text not null references challenge_registry(id) on delete cascade, metrics jsonb not null, captured_at timestamptz not null default now())")
            cur.execute("create index if not exists idx_challenge_metric_snapshots_challenge on challenge_metric_snapshots(challenge_id,captured_at desc)")
            cur.execute("create index if not exists idx_challenge_registry_expected_value on challenge_registry(expected_value_score desc, updated_at desc)")
            cur.execute("create index if not exists idx_challenge_registry_search_metrics on challenge_registry using gin(search_metrics)")

# Audit-chain ordering migration. PostgreSQL now() is transaction-scoped, so timestamp/id
# ordering is not a safe append order when several audit events are emitted in
# one transaction. Persist a monotonic sequence and repair legacy rows by their
# existing previous_hash links before new events use the sequence.
if _db:
    with psycopg.connect(_db) as conn:
        with conn.cursor() as cur:
            cur.execute("alter table audit_events add column if not exists audit_sequence bigserial")
            cur.execute("create unique index if not exists uq_audit_events_sequence on audit_events(audit_sequence)")
            cur.execute("select id,event_hash,previous_hash from audit_events order by audit_sequence asc")
            rows=cur.fetchall()
            if rows:
                by_previous={row[2]: row for row in rows if row[2]}
                by_hash={row[1]: row for row in rows}
                roots=[row for row in rows if not row[2] or row[2] not in by_hash]
                if len(roots) == 1:
                    ordered=[]
                    current=roots[0]
                    seen=set()
                    while current and current[0] not in seen:
                        seen.add(current[0])
                        ordered.append(current)
                        current=by_previous.get(current[1])
                    if len(ordered) == len(rows):
                        n=len(ordered)
                        for position,row in enumerate(ordered):
                            cur.execute(
                                "update audit_events set audit_sequence=%s where id=%s",
                                (position - n, row[0]),
                            )

# Ensure paused-assignment schema exists on existing production databases.
if _db:
    with psycopg.connect(_db) as conn:
        with conn.cursor() as cur:
            cur.execute("alter table job_assignments drop constraint if exists job_assignments_status_check")
            cur.execute("alter table job_assignments add constraint job_assignments_status_check check (status in ('ASSIGNED','RUNNING','PAUSED','COMPLETED','RELEASED','EXPIRED'))")
            cur.execute("create index if not exists idx_assignments_paused on job_assignments(worker_id,status,assigned_at desc) where status='PAUSED'")


# Explicit MCP OAuth identity mapping bootstrap.
# Keeps existing Railway databases compatible with the production migration.
if _db:
    with psycopg.connect(_db) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                create table if not exists mcp_oauth_identities (
                  id uuid primary key,
                  issuer text not null,
                  subject text not null,
                  account_id uuid not null references accounts(id) on delete cascade,
                  created_at timestamptz not null default now(),
                  last_seen_at timestamptz,
                  unique (issuer, subject)
                )
            """)
            cur.execute("create index if not exists idx_mcp_oauth_identities_account on mcp_oauth_identities(account_id)")


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
