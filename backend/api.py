import os
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

DATABASE_URL = os.environ.get("DATABASE_URL", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "")
SESSION_TTL = int(os.environ.get("SESSION_TTL_SECONDS", "3600"))

app = FastAPI(title="Satoshi Hunt API", version="0.1.0")


def db():
    if not DATABASE_URL:
        raise HTTPException(503, "DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL)


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


class ClaimCreate(BaseModel):
    candidate_hash: str = Field(min_length=32, max_length=128)
    result_status: str = Field(default="TESTED", pattern="^(TESTED|VERIFIED|REJECTED)$")
    cpu_seconds: int = Field(default=0, ge=0, le=86400)


@app.get("/health")
def health():
    return {"ok": True, "service": "satoshi-hunt-api", "custody": "non-custodial"}


@app.post("/auth/request-link")
def request_link(body: LinkRequest):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into accounts (id,email) values (%s,%s) on conflict (email) do nothing",
                (uuid4(), body.email.lower()),
            )
            cur.execute("select id from accounts where email=%s", (body.email.lower(),))
            row = cur.fetchone()
            cur.execute(
                "create table if not exists auth_links (email text primary key, token_hash text not null, expires_at timestamptz not null)"
            )
            cur.execute(
                "insert into auth_links(email,token_hash,expires_at) values(%s,%s,%s) "
                "on conflict(email) do update set token_hash=excluded.token_hash, expires_at=excluded.expires_at",
                (body.email.lower(), token_hash, datetime.now(timezone.utc) + timedelta(minutes=15)),
            )
    # Intentionally do not return the token. Production must deliver it through an email provider.
    return {"ok": True, "message": "If the address is eligible, a sign-in link will be sent."}


@app.post("/auth/verify")
def verify(body: VerifyRequest):
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select a.id from accounts a join auth_links l on l.email=a.email "
                "where a.email=%s and l.token_hash=%s and l.expires_at>now()",
                (body.email.lower(), token_hash),
            )
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


@app.post("/workers")
def create_worker(body: WorkerCreate, account_id: UUID = Depends(account_id_from_auth)):
    wid = uuid4()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("insert into workers(id,account_id,label) values(%s,%s,%s)", (wid, account_id, body.label))
    return {"id": str(wid), "label": body.label, "status": "ACTIVE"}


@app.get("/workers")
def list_workers(account_id: UUID = Depends(account_id_from_auth)):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id,label,status,registered_at,last_seen_at from workers where account_id=%s order by registered_at desc",
                (account_id,),
            )
            rows = cur.fetchall()
    return [{"id": str(r[0]), "label": r[1], "status": r[2], "registered_at": r[3], "last_seen_at": r[4]} for r in rows]


@app.post("/jobs")
def create_job(body: JobCreate, account_id: UUID = Depends(account_id_from_auth)):
    if body.scope != "public-reward-challenge":
        raise HTTPException(400, "Only public-reward-challenge jobs are allowed")
    jid = uuid4()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("insert into jobs(id,puzzle_id,scope) values(%s,%s,%s)", (jid, body.puzzle_id, body.scope))
    return {"id": str(jid), "puzzle_id": body.puzzle_id, "status": "QUEUED"}


@app.post("/jobs/{job_id}/claims")
def claim(job_id: UUID, body: ClaimCreate, account_id: UUID = Depends(account_id_from_auth)):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select j.id from jobs j where j.id=%s and j.scope='public-reward-challenge'",
                (job_id,),
            )
            if not cur.fetchone():
                raise HTTPException(404, "Job not found")
            cur.execute(
                "select w.id from workers w where w.account_id=%s and w.status='ACTIVE' order by last_seen_at desc nulls last limit 1",
                (account_id,),
            )
            worker = cur.fetchone()
            if not worker:
                raise HTTPException(400, "Register an active worker first")
            cid = uuid4()
            try:
                cur.execute(
                    "insert into work_claims(id,job_id,worker_id,candidate_hash,result_status,cpu_seconds,finished_at) "
                    "values(%s,%s,%s,%s,%s,%s,now())",
                    (cid, job_id, worker[0], body.candidate_hash, body.result_status, body.cpu_seconds),
                )
            except psycopg.errors.UniqueViolation:
                conn.rollback()
                return {"accepted": False, "reason": "DUPLICATE", "candidate_hash": body.candidate_hash}
    return {"accepted": True, "claim_id": str(cid), "result_status": body.result_status}


@app.get("/audit/account")
def audit_account(account_id: UUID = Depends(account_id_from_auth)):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from workers where account_id=%s",
                (account_id,),
            )
            workers = cur.fetchone()[0]
            cur.execute(
                "select coalesce(sum(seconds_verified),0) from worker_hours where account_id=%s",
                (account_id,),
            )
            seconds = cur.fetchone()[0]
            cur.execute(
                "select count(*) from reward_events where account_id=%s and settlement_status in ('APPROVED','SETTLED')",
                (account_id,),
            )
            rewards = cur.fetchone()[0]
    return {"workers": workers, "verified_worker_seconds": seconds, "approved_reward_events": rewards}
