import os
import hashlib
import json
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
import psycopg
import redis
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

DATABASE_URL = os.environ.get("DATABASE_URL", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "")
SESSION_TTL = int(os.environ.get("SESSION_TTL_SECONDS", "3600"))
ASSIGNMENT_TIMEOUT_SECONDS = max(30, int(os.environ.get("ASSIGNMENT_TIMEOUT_SECONDS", "120")))
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "")
RATE_LIMIT_REDIS_URL = os.environ.get("RATE_LIMIT_REDIS_URL", "")
_redis = redis.from_url(RATE_LIMIT_REDIS_URL, decode_responses=True) if RATE_LIMIT_REDIS_URL else None

app = FastAPI(title="Satoshi Hunt API", version="0.1.0")

if FRONTEND_ORIGIN:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[FRONTEND_ORIGIN],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

_RATE_WINDOW_SECONDS = 60
_RATE_LIMITS = {
    "auth_request": 5,
    "auth_verify": 10,
    "write": 60,
}
_rate_events = defaultdict(deque)


def enforce_rate_limit(request: Request, bucket: str) -> None:
    client = request.client.host if request.client else "unknown"
    if _redis:
        key = f"satoshi-hunt:rate:{bucket}:{client}"
        try:
            count = _redis.incr(key)
            if count == 1:
                _redis.expire(key, _RATE_WINDOW_SECONDS)
            if count > _RATE_LIMITS[bucket]:
                raise HTTPException(429, "Rate limit exceeded. Try again later.")
            return
        except HTTPException:
            raise
        except Exception:
            # Redis failure falls back to local development limiter rather than
            # silently disabling abuse protection.
            pass
    now = time.monotonic()
    key = (bucket, client)
    events = _rate_events[key]
    cutoff = now - _RATE_WINDOW_SECONDS
    while events and events[0] <= cutoff:
        events.popleft()
    if len(events) >= _RATE_LIMITS[bucket]:
        raise HTTPException(429, "Rate limit exceeded. Try again later.")
    events.append(now)


def db():
    if not DATABASE_URL:
        raise HTTPException(503, "DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL)


def record_audit_event(cur, event_type, entity_type, entity_id, account_id=None, worker_id=None, payload=None):
    payload = payload or {}
    cur.execute("select pg_advisory_xact_lock(7483921)")
    cur.execute("select event_hash from audit_events order by created_at desc, id desc limit 1")
    previous = cur.fetchone()
    previous_hash = previous[0] if previous else None
    canonical = json.dumps({
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "account_id": str(account_id) if account_id else None,
        "worker_id": str(worker_id) if worker_id else None,
        "payload": payload,
        "previous_hash": previous_hash,
    }, sort_keys=True, separators=(",", ":"), default=str).encode()
    event_hash = hashlib.sha256(canonical).hexdigest()
    cur.execute(
        "insert into audit_events(id,event_type,entity_type,entity_id,account_id,worker_id,payload,previous_hash,event_hash) values(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)",
        (uuid4(), event_type, entity_type, str(entity_id), account_id, worker_id, json.dumps(payload, default=str), previous_hash, event_hash),
    )
    return event_hash


def issue_session(account_id: UUID) -> str:
    if not JWT_SECRET:
        raise HTTPException(503, "JWT_SECRET is not configured")
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(account_id), "iat": now, "exp": now + timedelta(seconds=SESSION_TTL)},
        JWT_SECRET,
        algorithm="HS256",
    )


def account_id_from_auth(authorization: str = Header(default="")) -> UUID:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer session required")
    try:
        payload = jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
        return UUID(payload["sub"])
    except Exception:
        raise HTTPException(401, "Invalid or expired session")


class LinkRequest(BaseModel):
    email: EmailStr


class VerifyRequest(BaseModel):
    email: EmailStr
    token: str = Field(min_length=16, max_length=256)


class WorkerCreate(BaseModel):
    label: str = Field(default="worker", min_length=1, max_length=80)


class JobCreate(BaseModel):
    puzzle_id: str = Field(min_length=1, max_length=128)
    scope: str = "public-reward-challenge"


class AssignmentCreate(BaseModel):
    worker_id: UUID


def worker_id_from_token(authorization: str = Header(default="")) -> UUID:
    if not authorization.startswith("Worker "):
        raise HTTPException(401, "Worker token required")
    token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from workers where token_hash=%s and status='ACTIVE'", (token_hash,))
            row=cur.fetchone()
    if not row:
        raise HTTPException(401, "Invalid or revoked worker token")
    return row[0]


class ClaimCreate(BaseModel):
    assignment_id: UUID
    worker_id: UUID
    candidate_hash: str = Field(min_length=32, max_length=128)
    result_status: str = Field(default="TESTED", pattern="^(TESTED|VERIFIED|REJECTED)$")
    cpu_seconds: int = Field(default=0, ge=0, le=86400)


@app.get("/health")
def health():
    return {"ok": True, "service": "satoshi-hunt-api", "custody": "non-custodial"}


@app.post("/auth/request-link")
def request_link(body: LinkRequest, request: Request):
    enforce_rate_limit(request, "auth_request")
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("insert into accounts (id,email) values (%s,%s) on conflict (email) do nothing", (uuid4(), body.email.lower()))
            cur.execute("insert into auth_links(email,token_hash,expires_at) values(%s,%s,%s) on conflict(email) do update set token_hash=excluded.token_hash, expires_at=excluded.expires_at", (body.email.lower(), token_hash, datetime.now(timezone.utc) + timedelta(minutes=15)))
    return {"ok": True, "message": "If the address is eligible, a sign-in link will be sent."}


@app.post("/auth/verify")
def verify(body: VerifyRequest, request: Request):
    enforce_rate_limit(request, "auth_verify")
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select a.id from accounts a join auth_links l on l.email=a.email where a.email=%s and l.token_hash=%s and l.expires_at>now()", (body.email.lower(), token_hash))
            row = cur.fetchone()
            if not row:
                raise HTTPException(401, "Invalid or expired sign-in token")
            cur.execute("delete from auth_links where email=%s", (body.email.lower(),))
    return {"session": issue_session(row[0]), "expires_in": SESSION_TTL}


@app.get("/me")
def me(account_id: UUID = Depends(account_id_from_auth)):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select id,email,btc_payout_address,created_at from accounts where id=%s", (account_id,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Account not found")
    return {"id": str(row[0]), "email": row[1], "btc_payout_address": row[2], "created_at": row[3]}


def worker_owned(cur, worker_id: UUID, account_id: UUID, active_only=True):
    clause = " and status='ACTIVE'" if active_only else ""
    cur.execute(f"select id from workers where id=%s and account_id=%s{clause}", (worker_id, account_id))
    return cur.fetchone()


@app.post("/workers")
def create_worker(body: WorkerCreate, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    wid = uuid4()
    worker_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(worker_token.encode()).hexdigest()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("insert into workers(id,account_id,label,token_hash) values(%s,%s,%s,%s)", (wid, account_id, body.label, token_hash))
    return {"id": str(wid), "label": body.label, "status": "ACTIVE", "worker_token": worker_token}


@app.get("/workers")
def list_workers(account_id: UUID = Depends(account_id_from_auth)):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select id,label,status,registered_at,last_seen_at from workers where account_id=%s order by registered_at desc", (account_id,))
            rows = cur.fetchall()
    return [{"id": str(r[0]), "label": r[1], "status": r[2], "registered_at": r[3], "last_seen_at": r[4]} for r in rows]


@app.post("/workers/{worker_id}/heartbeat")
def worker_heartbeat(worker_id: UUID, request: Request, token_worker_id: UUID = Depends(worker_id_from_token)):
    enforce_rate_limit(request, "write")
    with db() as conn:
        with conn.cursor() as cur:
            if token_worker_id != worker_id:
                raise HTTPException(403, "Worker token does not match worker")
            cur.execute("select id from workers where id=%s and status='ACTIVE'", (worker_id,))
            if not cur.fetchone():
                raise HTTPException(404, "Worker not found")
            cur.execute("update workers set last_seen_at=now() where id=%s", (worker_id,))
    return {"ok": True, "worker_id": str(worker_id)}


@app.get("/jobs")
def list_jobs(account_id: UUID = Depends(account_id_from_auth)):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select j.id,j.puzzle_id,j.status,j.created_at,j.completed_at,a.id,a.worker_id,a.status,a.assigned_at,a.started_at,a.completed_at,a.last_heartbeat_at,a.verified_seconds from jobs j left join job_assignments a on a.job_id=j.id and a.status in ('ASSIGNED','RUNNING') where j.scope='public-reward-challenge' order by j.created_at desc limit 50")
            rows = cur.fetchall()
    return [{"id":str(r[0]),"puzzle_id":r[1],"status":r[2],"created_at":r[3],"completed_at":r[4],"assignment":None if r[5] is None else {"id":str(r[5]),"worker_id":str(r[6]),"status":r[7],"assigned_at":r[8],"started_at":r[9],"completed_at":r[10],"last_heartbeat_at":r[11],"contribution_seconds":r[12]}} for r in rows]


@app.get("/workers/{worker_id}/assignments")
def worker_assignments(worker_id: UUID, token_worker_id: UUID = Depends(worker_id_from_token)):
    with db() as conn:
        with conn.cursor() as cur:
            if token_worker_id != worker_id:
                raise HTTPException(403, "Worker token does not match worker")
            cur.execute(
                "select a.id,a.job_id,j.puzzle_id,a.status,a.assigned_at,a.started_at,"
                "a.completed_at,a.last_heartbeat_at,a.verified_seconds "
                "from job_assignments a join jobs j on j.id=a.job_id "
                "where a.worker_id=%s order by a.assigned_at desc limit 25",
                (worker_id,),
            )
            rows = cur.fetchall()
    return [{
        "id": str(r[0]), "job_id": str(r[1]), "puzzle_id": r[2], "status": r[3],
        "assigned_at": r[4], "started_at": r[5], "completed_at": r[6],
        "last_heartbeat_at": r[7], "verified_seconds": r[8]
    } for r in rows]


@app.get("/jobs/{job_id}")
def get_job(job_id: UUID, account_id: UUID = Depends(account_id_from_auth)):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select id,puzzle_id,scope,status,created_at,completed_at from jobs where id=%s and scope='public-reward-challenge'", (job_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Job not found")
            cur.execute("select id,worker_id,status,assigned_at,started_at,completed_at,last_heartbeat_at,verified_seconds from job_assignments where job_id=%s order by assigned_at desc limit 10", (job_id,))
            assignments = cur.fetchall()
    return {"id":str(row[0]),"puzzle_id":row[1],"scope":row[2],"status":row[3],"created_at":row[4],"completed_at":row[5],"assignments":[{"id":str(a[0]),"worker_id":str(a[1]),"status":a[2],"assigned_at":a[3],"started_at":a[4],"completed_at":a[5],"last_heartbeat_at":a[6],"contribution_seconds":a[7]} for a in assignments]}


@app.post("/jobs")
def create_job(body: JobCreate, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    if body.scope != "public-reward-challenge":
        raise HTTPException(400, "Only public-reward-challenge jobs are allowed")
    jid = uuid4()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("insert into jobs(id,puzzle_id,scope) values(%s,%s,%s)", (jid, body.puzzle_id, body.scope))
    return {"id":str(jid),"puzzle_id":body.puzzle_id,"status":"QUEUED"}


@app.post("/jobs/{job_id}/assign")
def assign_job(job_id: UUID, body: AssignmentCreate, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    aid = uuid4()
    with db() as conn:
        with conn.cursor() as cur:
            expire_stale_assignments(cur)
            cur.execute("select id,status from jobs where id=%s and scope='public-reward-challenge' for update", (job_id,))
            job = cur.fetchone()
            if not job:
                raise HTTPException(404, "Job not found")
            if job[1] != "QUEUED":
                raise HTTPException(409, f"Job is not assignable from {job[1]} state")
            if not worker_owned(cur, body.worker_id, account_id):
                raise HTTPException(400, "Selected worker is not active or does not belong to this account")
            cur.execute("select id from job_assignments where job_id=%s and status in ('ASSIGNED','RUNNING') for update", (job_id,))
            if cur.fetchone():
                raise HTTPException(409, "Job is already assigned")
            cur.execute("insert into job_assignments(id,job_id,worker_id,status) values(%s,%s,%s,'ASSIGNED')", (aid,job_id,body.worker_id))
    return {"assignment_id":str(aid),"job_id":str(job_id),"worker_id":str(body.worker_id),"status":"ASSIGNED"}


def expire_stale_assignments(cur):
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=ASSIGNMENT_TIMEOUT_SECONDS)
    cur.execute(
        "update job_assignments set status='EXPIRED',expired_at=now() "
        "where status in ('ASSIGNED','RUNNING') "
        "and coalesce(last_heartbeat_at,assigned_at) < %s returning job_id",
        (cutoff,),
    )
    for (job_id,) in cur.fetchall():
        cur.execute(
            "update jobs set status='QUEUED',completed_at=null "
            "where id=%s and status in ('RUNNING','QUEUED')",
            (job_id,),
        )


def assignment_for_worker(cur, assignment_id: UUID, worker_id: UUID):
    cur.execute("select id,job_id,worker_id,status,started_at from job_assignments where id=%s and worker_id=%s", (assignment_id, worker_id))
    return cur.fetchone()


def assignment_for_account(cur, assignment_id: UUID, account_id: UUID):
    cur.execute("select a.id,a.job_id,a.worker_id,a.status,j.status from job_assignments a join workers w on w.id=a.worker_id join jobs j on j.id=a.job_id where a.id=%s and w.account_id=%s for update", (assignment_id,account_id))
    return cur.fetchone()


@app.post("/assignments/{assignment_id}/start")
def start_assignment(assignment_id: UUID, request: Request, token_worker_id: UUID = Depends(worker_id_from_token)):
    enforce_rate_limit(request, "write")
    now = datetime.now(timezone.utc)
    with db() as conn:
        with conn.cursor() as cur:
            expire_stale_assignments(cur)
            row=assignment_for_worker(cur,assignment_id,token_worker_id)
            if not row: raise HTTPException(404,"Assignment not found")
            if row[3]!="ASSIGNED": raise HTTPException(409,f"Assignment is {row[3]}")
            cur.execute("update job_assignments set status='RUNNING',started_at=%s,last_heartbeat_at=%s where id=%s",(now,now,assignment_id))
            cur.execute("update jobs set status='RUNNING' where id=%s and status='QUEUED'",(row[1],))
            record_audit_event(cur,"STARTED","assignment",assignment_id,worker_id=token_worker_id,payload={"job_id":str(row[1])})
    return {"assignment_id":str(assignment_id),"status":"RUNNING","started_at":now}


@app.post("/assignments/{assignment_id}/heartbeat")
def assignment_heartbeat(assignment_id: UUID, request: Request, token_worker_id: UUID = Depends(worker_id_from_token)):
    enforce_rate_limit(request, "write")
    now=datetime.now(timezone.utc)
    with db() as conn:
        with conn.cursor() as cur:
            row=assignment_for_worker(cur,assignment_id,token_worker_id)
            if not row: raise HTTPException(404,"Assignment not found")
            if row[3]!="RUNNING": raise HTTPException(409,f"Assignment is {row[3]}")
            cur.execute("update job_assignments set last_heartbeat_at=%s where id=%s",(now,assignment_id))
            cur.execute("update workers set last_seen_at=%s where id=%s",(now,row[2]))
            record_audit_event(cur,"HEARTBEAT","assignment",assignment_id,worker_id=token_worker_id,payload={"job_id":str(row[1])})
    return {"assignment_id":str(assignment_id),"status":"RUNNING","heartbeat_at":now}


@app.post("/assignments/{assignment_id}/complete")
def complete_assignment(assignment_id: UUID, request: Request, token_worker_id: UUID = Depends(worker_id_from_token)):
    enforce_rate_limit(request, "write")
    now=datetime.now(timezone.utc)
    with db() as conn:
        with conn.cursor() as cur:
            row=assignment_for_account(cur,assignment_id,account_id)
            if not row: raise HTTPException(404,"Assignment not found")
            if row[3]!="RUNNING": raise HTTPException(409,f"Assignment is {row[3]}")
            cur.execute("select extract(epoch from (%s-started_at))::bigint from job_assignments where id=%s",(now,assignment_id))
            seconds=max(0,int(cur.fetchone()[0] or 0))
            cur.execute("update job_assignments set status='COMPLETED',completed_at=%s,last_heartbeat_at=%s,verified_seconds=%s where id=%s",(now,now,seconds,assignment_id))
            cur.execute("update jobs set status='COMPLETED',completed_at=%s where id=%s and status='RUNNING'",(now,row[1]))
            cur.execute("insert into worker_hours(id,account_id,worker_id,period_start,seconds_verified) values(%s,%s,%s,current_date,%s) on conflict(worker_id,period_start) do update set seconds_verified=worker_hours.seconds_verified+excluded.seconds_verified",(uuid4(),account_id,row[2],seconds))
            record_audit_event(cur,"COMPLETED","assignment",assignment_id,account_id,row[2],{"job_id":str(row[1]),"contribution_seconds":seconds})
    return {"assignment_id":str(assignment_id),"status":"COMPLETED","contribution_seconds":seconds}


@app.post("/jobs/{job_id}/claims")
def claim(job_id: UUID, body: ClaimCreate, request: Request, token_worker_id: UUID = Depends(worker_id_from_token)):
    enforce_rate_limit(request, "write")
    with db() as conn:
        with conn.cursor() as cur:
            expire_stale_assignments(cur)
            cur.execute(
                "select a.id,a.worker_id,a.status,j.status from job_assignments a "
                "join jobs j on j.id=a.job_id join workers w on w.id=a.worker_id "
                "where a.id=%s and a.job_id=%s and w.id=%s for update",
                (body.assignment_id, job_id, token_worker_id),
            )
            assignment = cur.fetchone()
            if not assignment: raise HTTPException(404,"Assignment not found")
            if token_worker_id != body.worker_id or assignment[1] != token_worker_id:
                raise HTTPException(403,"Worker token does not match claim worker")
            if assignment[2] not in ("ASSIGNED","RUNNING","COMPLETED"): raise HTTPException(409,"Assignment is no longer claimable")
            cid=uuid4()
            try:
                cur.execute("insert into work_claims(id,job_id,worker_id,candidate_hash,result_status,cpu_seconds,finished_at) values(%s,%s,%s,%s,%s,%s,now())",(cid,job_id,body.worker_id,body.candidate_hash,body.result_status,body.cpu_seconds))
            except psycopg.errors.UniqueViolation:
                conn.rollback()
                return {"accepted":False,"reason":"DUPLICATE","candidate_hash":body.candidate_hash}
            record_audit_event(cur,"CLAIM_SUBMITTED","job",job_id,worker_id=token_worker_id,payload={"assignment_id":str(body.assignment_id),"candidate_hash":body.candidate_hash,"result_status":body.result_status})
            if body.result_status == "VERIFIED":
                cur.execute(
                    "update jobs set status='VERIFIED',completed_at=coalesce(completed_at,now()) "
                    "where id=%s and status in ('RUNNING','COMPLETED')",
                    (job_id,),
                )
    return {"accepted":True,"claim_id":str(cid),"result_status":body.result_status,"assignment_id":str(body.assignment_id)}


@app.get("/audit/job/{job_id}")
def public_job_audit(job_id: UUID):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select id,puzzle_id,status,created_at,completed_at from jobs where id=%s and scope='public-reward-challenge'", (job_id,))
            job=cur.fetchone()
            if not job: raise HTTPException(404,"Job not found")
            cur.execute("select count(*),coalesce(sum(verified_seconds),0) from job_assignments where job_id=%s and status='COMPLETED'", (job_id,))
            assignments,seconds=cur.fetchone()
            cur.execute("select count(*),count(*) filter (where result_status='VERIFIED'),count(*) filter (where result_status='REJECTED') from work_claims where job_id=%s", (job_id,))
            claims,verified,rejected=cur.fetchone()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select event_type,entity_type,entity_id,worker_id,payload,previous_hash,event_hash,created_at from audit_events where (entity_type='job' and entity_id=%s) or (entity_type='assignment' and entity_id in (select id::text from job_assignments where job_id=%s)) order by created_at asc,id asc", (str(job_id), job_id))
            events=cur.fetchall()
    return {"job_id":str(job[0]),"puzzle_id":job[1],"status":job[2],"created_at":job[3],"completed_at":job[4],
            "completed_assignments":assignments,"contribution_seconds":seconds,"claims":claims,
            "verified_claims":verified,"rejected_claims":rejected,
            "audit_events":[{"event_type":e[0],"entity_type":e[1],"entity_id":e[2],"worker_id":str(e[3]) if e[3] else None,"payload":e[4],"previous_hash":e[5],"event_hash":e[6],"created_at":e[7]} for e in events]}


@app.get("/audit/account")
def audit_account(account_id: UUID = Depends(account_id_from_auth)):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from workers where account_id=%s",(account_id,))
            workers=cur.fetchone()[0]
            cur.execute("select coalesce(sum(seconds_verified),0) from worker_hours where account_id=%s",(account_id,))
            seconds=cur.fetchone()[0]
            cur.execute("select count(*) from reward_events where account_id=%s and settlement_status in ('APPROVED','SETTLED')",(account_id,))
            rewards=cur.fetchone()[0]
            cur.execute("select count(*) from work_claims c join workers w on w.id=c.worker_id where w.account_id=%s and c.result_status='VERIFIED'",(account_id,))
            verified_claims=cur.fetchone()[0]
            cur.execute("select count(*) from work_claims c join workers w on w.id=c.worker_id where w.account_id=%s and c.result_status='REJECTED'",(account_id,))
            rejected_claims=cur.fetchone()[0]
    reliability=round((verified_claims/(verified_claims+rejected_claims))*100,2) if verified_claims+rejected_claims else 0.0
    return {"workers":workers,"contributed_worker_seconds":seconds,"approved_reward_events":rewards,"verified_claims":verified_claims,"rejected_claims":rejected_claims,"reliability_score":reliability}


@app.post("/jobs/{job_id}/verify")
def verify_job(job_id: UUID, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    """Mark a completed public-challenge job verified only after an adapter has
    independently validated its submitted candidate. This endpoint intentionally
    does not perform private-key or wallet access."""
    enforce_rate_limit(request, "write")
    raise HTTPException(
        501,
        "Challenge-specific verification adapter is required before a reward result can be verified.",
    )
