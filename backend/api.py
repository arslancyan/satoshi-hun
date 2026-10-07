import os
import hashlib
import base64
import hmac
import re
import json
import logging
import secrets
import time
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import jwt
import psycopg
import redis
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from verifier import verify_candidate_hash
from settlement import build_reward_event
from protocol_v1 import proof_hash, capability_score, adaptive_ranges, reliability_score, economic_priority
from anti_cheat import security_flags, reputation_score
from payouts import validate_external_txid
from owner_config import OWNER_PLATFORM_FEE_BTC_ADDRESS

DATABASE_URL = os.environ.get("DATABASE_URL", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "")
SESSION_TTL = int(os.environ.get("SESSION_TTL_SECONDS", "3600"))
ASSIGNMENT_TIMEOUT_SECONDS = max(30, int(os.environ.get("ASSIGNMENT_TIMEOUT_SECONDS", "120")))
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "https://arslancyan.github.io").strip()
CHALLENGE_INGESTION_KEY = os.environ.get("CHALLENGE_INGESTION_KEY", "")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "").strip().lower()
RATE_LIMIT_REDIS_URL = os.environ.get("RATE_LIMIT_REDIS_URL", "")
MAX_ACTIVE_ASSIGNMENTS = max(1, int(os.environ.get("MAX_ACTIVE_ASSIGNMENTS", "100")))
MAX_ACTIVE_ASSIGNMENTS_PER_JOB = max(1, int(os.environ.get("MAX_ACTIVE_ASSIGNMENTS_PER_JOB", "1000")))
MAX_NETWORK_WORKER_HOURS_PER_DAY = max(1, int(os.environ.get("MAX_NETWORK_WORKER_HOURS_PER_DAY", "10000")))
PAYOUT_WORKER_TOKEN = os.environ.get("PAYOUT_WORKER_TOKEN", "").strip()
MAX_SINGLE_PAYOUT_BTC = Decimal(os.environ.get("MAX_SINGLE_PAYOUT_BTC", "0.001"))
MAX_DAILY_PAYOUT_BTC = Decimal(os.environ.get("MAX_DAILY_PAYOUT_BTC", "0.005"))
PAYOUT_RETRY_AFTER_MINUTES = max(5, int(os.environ.get("PAYOUT_RETRY_AFTER_MINUTES", "15")))
PAYOUT_SIGNER_TOKEN = os.environ.get("PAYOUT_SIGNER_TOKEN", "").strip()
TREASURY_BTC_ADDRESS = os.environ.get("TREASURY_BTC_ADDRESS", "bc1ptstlyntypqqf8s5qz3jwcsrxw2pxqj634c7pklj2mjlvqwl22l6qqq8csl").strip()
TREASURY_WALLET_ID = UUID("00000000-0000-0000-0000-000000000001")
_redis = redis.from_url(RATE_LIMIT_REDIS_URL, decode_responses=True) if RATE_LIMIT_REDIS_URL else None

app = FastAPI(title="Satoshi Hunt API", version="0.1.1")

# Managed solver state. A RUN from the website starts a real server-side solver
# for that assignment, so users do not need to install or operate worker.py.
_MANAGED_SOLVERS = {}
_MANAGED_SOLVERS_LOCK = threading.Lock()


def _managed_hash_digest(algorithm, message):
    algorithm = str(algorithm).lower()
    if algorithm == "sha256":
        return hashlib.sha256(message).digest()
    if algorithm == "ripemd160":
        return hashlib.new("ripemd160", message).digest()
    if algorithm == "hash160":
        return hashlib.new("ripemd160", hashlib.sha256(message).digest()).digest()
    if algorithm == "hash256":
        return hashlib.sha256(hashlib.sha256(message).digest()).digest()
    raise ValueError("Unsupported collision algorithm")


def _stop_managed_solver(assignment_id):
    with _MANAGED_SOLVERS_LOCK:
        state = _MANAGED_SOLVERS.get(str(assignment_id))
        if state:
            state["stop"].set()


def _start_managed_solver(assignment_id, job_id, worker_id):
    key = str(assignment_id)
    with _MANAGED_SOLVERS_LOCK:
        current = _MANAGED_SOLVERS.get(key)
        if current and current["thread"].is_alive():
            return
        stop = threading.Event()
        state = {"stop": stop}
        _MANAGED_SOLVERS[key] = state

    def runner():
        seen = {}
        cursor = 0
        last_heartbeat = 0.0
        last_checkpoint = 0.0
        started = time.monotonic()
        try:
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "select c.challenge_type,c.verification,c.status,c.balance_btc "
                        "from jobs j join challenge_registry c on c.id=j.puzzle_id "
                        "where j.id=%s",
                        (job_id,),
                    )
                    challenge = cur.fetchone()
            if not challenge or challenge[2] != "OPEN + FUNDED" or Decimal(str(challenge[3] or 0)) <= 0:
                return
            allowed = (challenge[1] or {}).get("allowed_algorithms") or []
            algorithm = next((str(x).lower() for x in allowed if str(x).lower() in {"sha256","ripemd160","hash160","hash256"}), "")
            if not algorithm:
                return

            max_candidates = max(0, int(os.environ.get("SATOSHI_HUNT_MANAGED_MAX_CANDIDATES", "0")))
            max_memory_mb = max(32, int(os.environ.get("SATOSHI_HUNT_MANAGED_MAX_MEMORY_MB", "128")))
            max_entries = max(1000, (max_memory_mb * 1024 * 1024) // 96)

            # Deterministically partition the 64-bit search space by worker.
            # Each worker gets a 48-bit lane and advances by 2^48, so multiple
            # workers on the same puzzle do not all restart at cursor zero.
            lane_material = f"{job_id}:{worker_id}".encode()
            lane = int.from_bytes(hashlib.sha256(lane_material).digest()[:6], "big")
            lane_step = 1 << 48
            cursor = lane
            search_end = (1 << 64) - 1
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "update job_assignments set status='RUNNING',started_at=coalesce(started_at,now()),last_heartbeat_at=now() "
                        "where id=%s and worker_id=%s and status in ('ASSIGNED','RUNNING')",
                        (assignment_id, worker_id),
                    )
                    cur.execute("update jobs set status='RUNNING' where id=%s and status='QUEUED'", (job_id,))
                    record_audit_event(cur, "AUTO_SOLVER_STARTED", "assignment", assignment_id, worker_id=worker_id,
                                        payload={"job_id":str(job_id),"algorithm":algorithm,"mode":"managed_server_solver"})

            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "select cursor_start,cursor_end,cursor_next from job_checkpoints "
                        "where assignment_id=%s order by created_at desc,id desc limit 1",
                        (assignment_id,),
                    )
                    previous_checkpoint = cur.fetchone()
            if previous_checkpoint and previous_checkpoint[0] == lane and previous_checkpoint[1] == search_end:
                cursor = max(lane, int(previous_checkpoint[2]))

            lane_candidates = 0
            while not stop.is_set():
                if max_candidates and lane_candidates >= max_candidates:
                    break
                if cursor >= search_end:
                    break
                # If an operator/user stop or stale-expiry released the
                # assignment, terminate the managed solver promptly even if
                # the stop event was not observed in the same process.
                with db() as conn:
                    with conn.cursor() as cur:
                        cur.execute("select status from job_assignments where id=%s", (assignment_id,))
                        current_assignment = cur.fetchone()
                if not current_assignment or current_assignment[0] != "RUNNING":
                    break
                message = b"satoshi-hunt:" + cursor.to_bytes(8, "big")
                digest = _managed_hash_digest(algorithm, message)
                previous = seen.get(digest)
                if previous is not None and previous != message:
                    candidate = f"{algorithm}:{previous.hex()}:{message.hex()}"
                    with db() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                "select id from work_claims where job_id=%s and worker_id=%s and candidate_hash=%s limit 1",
                                (job_id, worker_id, candidate),
                            )
                            if not cur.fetchone():
                                claim_id = uuid4()
                                cur.execute(
                                    "insert into work_claims(id,job_id,worker_id,candidate_hash,result_status,cpu_seconds,finished_at) "
                                    "values(%s,%s,%s,%s,'TESTED',%s,now())",
                                    (claim_id,job_id,worker_id,candidate,max(0,int(time.monotonic()-started))),
                                )
                                result = auto_credit_verified_claim(cur, job_id, claim_id, worker_id, candidate)
                                record_audit_event(cur, "AUTO_SOLVER_RESULT", "assignment", assignment_id, worker_id=worker_id,
                                                    payload={"job_id":str(job_id),"verified":bool(result and result.get("verified"))})
                    if result and result.get("verified"):
                        with db() as conn:
                            with conn.cursor() as cur:
                                cur.execute(
                                    "update job_assignments set status='COMPLETED',completed_at=now(),last_heartbeat_at=now() where id=%s",
                                    (assignment_id,),
                                )
                        return
                seen[digest] = message
                cursor += lane_step
                lane_candidates += 1
                if len(seen) >= max_entries:
                    seen.clear()
                now = time.monotonic()
                if now - last_heartbeat >= 10:
                    with db() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                "select status from job_assignments where id=%s for update",
                                (assignment_id,),
                            )
                            assignment_row = cur.fetchone()
                            if not assignment_row or assignment_row[0] != "RUNNING":
                                # Never keep hashing after the database says this
                                # assignment was stopped, switched, or expired.
                                stop.set()
                                break
                            cur.execute(
                                "update job_assignments set last_heartbeat_at=now() where id=%s and status='RUNNING'",
                                (assignment_id,),
                            )
                    last_heartbeat = now
                if now - last_checkpoint >= 30:
                    with db() as conn:
                        with conn.cursor() as cur:
                            digest_checkpoint = proof_hash(
                                job_id, assignment_id, lane, search_end, cursor, str(cursor)
                            )
                            cur.execute(
                                "insert into job_checkpoints(id,job_id,assignment_id,cursor_start,cursor_end,cursor_next,checkpoint_hash) "
                                "values(%s,%s,%s,%s,%s,%s,%s)",
                                (uuid4(), job_id, assignment_id, lane, search_end, cursor, digest_checkpoint),
                            )
                            cur.execute(
                                "insert into work_proofs(id,assignment_id,worker_id,proof_type,proof_hash,nonce) "
                                "values(%s,%s,%s,'CHECKPOINT',%s,%s) on conflict do nothing",
                                (uuid4(), assignment_id, worker_id, digest_checkpoint, str(cursor)),
                            )
                    last_checkpoint = now
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "update job_assignments set status='COMPLETED',completed_at=now(),last_heartbeat_at=null "
                        "where id=%s and status='RUNNING'",
                        (assignment_id,),
                    )
                    cur.execute(
                        "update jobs set status='QUEUED' where id=%s and status='RUNNING' "
                        "and not exists (select 1 from job_assignments where job_id=%s and status in ('ASSIGNED','RUNNING'))",
                        (job_id,job_id),
                    )
                    record_audit_event(cur, "AUTO_SOLVER_STOPPED", "assignment", assignment_id, worker_id=worker_id,
                                        payload={"job_id":str(job_id),"cursor":cursor,"reason":"stop_or_bound"})
        except Exception as exc:
            logging.exception("Managed solver failed for assignment %s: %s", assignment_id, type(exc).__name__)
            try:
                with db() as conn:
                    with conn.cursor() as cur:
                        cur.execute("update job_assignments set status='RELEASED',last_heartbeat_at=null where id=%s and status in ('ASSIGNED','RUNNING')", (assignment_id,))
                        record_audit_event(cur, "AUTO_SOLVER_ERROR", "assignment", assignment_id, worker_id=worker_id,
                                            payload={"job_id":str(job_id),"error":type(exc).__name__})
            except Exception:
                logging.exception("Could not release failed managed solver assignment %s", assignment_id)
        finally:
            with _MANAGED_SOLVERS_LOCK:
                _MANAGED_SOLVERS.pop(key, None)

    thread = threading.Thread(target=runner, name=f"managed-solver-{key[:8]}", daemon=True)
    state["thread"] = thread
    thread.start()


def _recover_managed_solvers():
    """Resume website-started solvers after an API process restart/deploy."""
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """select a.id,a.job_id,a.worker_id
                       from job_assignments a
                       join jobs j on j.id=a.job_id
                       join challenge_registry c on c.id=j.puzzle_id
                       where a.status='RUNNING'
                         and j.scope='public-reward-challenge'
                         and c.status='OPEN + FUNDED'
                         and c.balance_btc>0
                       order by a.started_at asc"""
                )
                assignments=cur.fetchall()
        for assignment_id,job_id,worker_id in assignments:
            _start_managed_solver(assignment_id,job_id,worker_id)
    except Exception:
        logging.exception("Could not recover managed solvers after startup")


@app.on_event("startup")
def recover_managed_solvers():
    # Run recovery in a background thread so API startup/health checks are not
    # blocked by database work or solver initialization.
    threading.Thread(
        target=_recover_managed_solvers,
        name="managed-solver-recovery",
        daemon=True,
    ).start()


@app.on_event("startup")
def validate_treasury_configuration():
    if not valid_btc_mainnet_address(TREASURY_BTC_ADDRESS):
        raise RuntimeError("TREASURY_BTC_ADDRESS is not a valid Bitcoin mainnet address")


ALLOWED_FRONTEND_ORIGINS = list(dict.fromkeys(
    origin for origin in (FRONTEND_ORIGIN, "https://arslancyan.github.io") if origin
))

if ALLOWED_FRONTEND_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["*"],
    )

@app.middleware("http")
async def enforce_public_cors_headers(request: Request, call_next):
    response = await call_next(request)
    origin = request.headers.get("origin")
    if origin in ALLOWED_FRONTEND_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        if request.method == "OPTIONS" and request.headers.get("access-control-request-method"):
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Idempotency-Key"
    return response


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
        except Exception as exc:
            # Redis failure falls back to local development limiter rather than
            # silently disabling abuse protection.
            logging.warning("Redis rate limiter unavailable: %s", type(exc).__name__)
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

def treasury_available_btc(cur) -> Decimal:
    cur.execute("select funded_btc-reserved_btc from treasury_accounting where id=%s for update", (TREASURY_WALLET_ID,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(503, "Treasury accounting is not initialized")
    return Decimal(str(row[0]))

def treasury_config(cur):
    cur.execute("select address,network,status from treasury_wallets where id=%s", (TREASURY_WALLET_ID,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(503, "Treasury wallet is not initialized")
    return {"address": row[0], "network": row[1], "status": row[2]}

def treasury_ledger(cur, entry_type, amount, reference_type, reference_id=None, account_id=None, destination_btc_address=None):
    cur.execute(
        "insert into treasury_ledger(id,wallet_id,entry_type,amount_btc,reference_type,reference_id,account_id,destination_btc_address) "
        "values(%s,%s,%s,%s,%s,%s,%s,%s)",
        (uuid4(), TREASURY_WALLET_ID, entry_type, amount, reference_type,
         str(reference_id) if reference_id else None, account_id, destination_btc_address),
    )


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
        if not JWT_SECRET:
            raise HTTPException(503, "JWT_SECRET is not configured")
        payload = jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
        return UUID(payload["sub"])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "Invalid or expired session")


PASSWORD_ITERATIONS = max(210000, int(os.environ.get("PASSWORD_PBKDF2_ITERATIONS", "310000")))
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BECH32M_CONST = 0x2bc830a3

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "pbkdf2_sha256$" + str(PASSWORD_ITERATIONS) + "$" + salt.hex() + "$" + digest.hex()

def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256": return False
        iterations = int(iterations)
        if iterations < 210000 or iterations > 2000000: return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations)
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

def _base58check_valid(address: str) -> bool:
    if not address or any(c not in BASE58_ALPHABET for c in address): return False
    n = 0
    for c in address: n = n * 58 + BASE58_ALPHABET.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    leading = len(address) - len(address.lstrip("1"))
    raw = b"\x00" * leading + raw
    return len(raw) == 25 and raw[0] in (0, 5) and hashlib.sha256(hashlib.sha256(raw[:-4]).digest()).digest()[:4] == raw[-4:]

def _bech32_polymod(values):
    generator = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for value in values:
        top = chk >> 25
        chk = ((chk & 0x1ffffff) << 5) ^ value
        for i in range(5):
            if (top >> i) & 1: chk ^= generator[i]
    return chk

def _bech32_hrp_expand(hrp): return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]

def _convertbits(data, frombits, tobits, pad=False):
    acc = 0; bits = 0; ret = []; maxv = (1 << tobits) - 1; max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or value >> frombits: return None
        acc = ((acc << frombits) | value) & max_acc; bits += frombits
        while bits >= tobits:
            bits -= tobits; ret.append((acc >> bits) & maxv)
    if pad:
        if bits: ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv): return None
    return ret

def _bech32_valid(address: str) -> bool:
    if not address or (address.lower() != address and address.upper() != address): return False
    address = address.lower()
    if not address.startswith("bc1") or len(address) > 90: return False
    pos = address.rfind("1")
    if pos < 1 or pos + 7 > len(address): return False
    try: data = [BECH32_CHARSET.index(c) for c in address[pos + 1:]]
    except ValueError: return False
    polymod = _bech32_polymod(_bech32_hrp_expand(address[:pos]) + data)
    spec = 1 if polymod == 1 else BECH32M_CONST if polymod == BECH32M_CONST else None
    if spec is None or not data: return False
    version = data[0]; decoded = _convertbits(data[1:-6], 5, 8, False)
    if version > 16 or decoded is None or not 2 <= len(decoded) <= 40: return False
    if version == 0: return spec == 1 and len(decoded) in (20, 32)
    return spec == BECH32M_CONST

def valid_btc_mainnet_address(address: str) -> bool:
    value = address.strip()
    return _base58check_valid(value) or _bech32_valid(value)

class LinkRequest(BaseModel):
    email: EmailStr


class VerifyRequest(BaseModel):
    email: EmailStr
    token: str = Field(min_length=16, max_length=256)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class WorkerCreate(BaseModel):
    label: str = Field(default="worker", min_length=1, max_length=80)


class ChallengeIngest(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    challenge_type: str = Field(min_length=1, max_length=80)
    reward_btc: float = Field(gt=0)
    balance_btc: float = Field(ge=0)
    status: str
    rules: str = "public-reward-challenge"
    provenance: dict
    verification: dict


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




def worker_idempotency_fingerprint(request: Request, worker_id: UUID, payload) -> str:
    canonical = json.dumps(
        {"worker_id": str(worker_id), "method": request.method, "path": request.url.path, "payload": payload},
        sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def worker_idempotency_replay(cur, worker_id: UUID, request: Request, payload):
    key = idempotency_key(request)
    if not key:
        return None
    fingerprint = worker_idempotency_fingerprint(request, worker_id, payload)
    cur.execute(
        "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"satoshi-hunt:worker-idempotency:{worker_id}:{key}",),
    )
    cur.execute(
        "select request_hash,response_json from worker_idempotency_records "
        "where worker_id=%s and idempotency_key=%s",
        (worker_id, key),
    )
    row = cur.fetchone()
    if not row:
        return None
    if row[0] != fingerprint:
        raise HTTPException(409, "Idempotency-Key was already used with a different request")
    return row[1]


def worker_idempotency_store(cur, worker_id: UUID, request: Request, payload, response):
    key = idempotency_key(request)
    if not key:
        return
    fingerprint = worker_idempotency_fingerprint(request, worker_id, payload)
    cur.execute(
        "insert into worker_idempotency_records(worker_id,idempotency_key,request_hash,response_json) "
        "values(%s,%s,%s,%s::jsonb) on conflict(worker_id,idempotency_key) do nothing",
        (worker_id, key, fingerprint, json.dumps(response, default=str)),
    )


class CapabilityUpdate(BaseModel):
    cpu_threads: int = Field(default=1, ge=1, le=1024)
    memory_mb: int = Field(default=512, ge=1)
    adapter_types: list[str] = Field(default_factory=list, max_length=50)


class CheckpointCreate(BaseModel):
    assignment_id: UUID
    cursor_start: int = Field(ge=0)
    cursor_end: int = Field(gt=0)
    cursor_next: int = Field(ge=0)
    nonce: str = Field(default="", max_length=128)


class CreatorChallenge(BaseModel):
    challenge_id: str = Field(min_length=1, max_length=128)
    terms: dict = Field(default_factory=dict)


class ClaimCreate(BaseModel):
    assignment_id: UUID
    worker_id: UUID
    candidate_hash: str = Field(min_length=32, max_length=128)
    result_status: str = Field(default="TESTED", pattern="^(TESTED|REJECTED)$")
    cpu_seconds: int = Field(default=0, ge=0, le=86400)



@app.put("/workers/{worker_id}/capabilities")
def update_capabilities(worker_id: UUID, body: CapabilityUpdate, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload=body.model_dump()
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            if not worker_owned(cur, worker_id, account_id, active_only=True):
                raise HTTPException(404, "Worker not found")
            cur.execute(
                "insert into worker_capabilities(worker_id,cpu_threads,memory_mb,adapter_types,updated_at) values(%s,%s,%s,%s::jsonb,now()) "
                "on conflict(worker_id) do update set cpu_threads=excluded.cpu_threads,memory_mb=excluded.memory_mb,adapter_types=excluded.adapter_types,updated_at=now()",
                (worker_id,body.cpu_threads,body.memory_mb,json.dumps(body.adapter_types)),
            )
            record_audit_event(cur,"WORKER_CAPABILITIES_UPDATED","worker",worker_id,account_id,worker_id,payload=body.model_dump())
            response={"worker_id":str(worker_id),"capabilities":body.model_dump()}
            idempotency_store(cur, account_id, request, payload, response)
            return response

@app.post("/assignments/{assignment_id}/checkpoint")
def checkpoint(assignment_id: UUID, body: CheckpointCreate, request: Request, worker_id: UUID = Depends(worker_id_from_token)):
    enforce_rate_limit(request, "write")
    if body.cursor_next > body.cursor_end or body.cursor_end <= body.cursor_start:
        raise HTTPException(400, "Invalid checkpoint cursor")
    payload=body.model_dump()
    with db() as conn:
        with conn.cursor() as cur:
            replay=worker_idempotency_replay(cur, worker_id, request, payload)
            if replay is not None:
                return replay
            cur.execute(
                "select a.job_id,a.worker_id,a.status from job_assignments a where a.id=%s and a.worker_id=%s for update",
                (assignment_id,worker_id),
            )
            row=cur.fetchone()
            if not row or row[2] not in ("ASSIGNED","RUNNING"):
                raise HTTPException(409,"Assignment is not active")
            cur.execute(
                "select cursor_start,cursor_end,cursor_next from job_checkpoints "
                "where assignment_id=%s order by created_at desc,id desc limit 1 for update",
                (assignment_id,),
            )
            previous_checkpoint=cur.fetchone()
            if previous_checkpoint:
                if body.cursor_start != previous_checkpoint[0] or body.cursor_end != previous_checkpoint[1]:
                    raise HTTPException(409, "Checkpoint range changed for this assignment")
                if body.cursor_next <= previous_checkpoint[2]:
                    raise HTTPException(409, "Checkpoint cursor must advance monotonically")
            digest=proof_hash(row[0],assignment_id,body.cursor_start,body.cursor_end,body.cursor_next,body.nonce)
            cur.execute(
                "insert into job_checkpoints(id,job_id,assignment_id,cursor_start,cursor_end,cursor_next,checkpoint_hash) values(%s,%s,%s,%s,%s,%s,%s)",
                (uuid4(),row[0],assignment_id,body.cursor_start,body.cursor_end,body.cursor_next,digest),
            )
            cur.execute(
                "insert into work_proofs(id,assignment_id,worker_id,proof_type,proof_hash,nonce) values(%s,%s,%s,'CHECKPOINT',%s,%s) on conflict do nothing",
                (uuid4(),assignment_id,worker_id,digest,body.nonce),
            )
            response={"checkpoint_hash":digest,"cursor_next":body.cursor_next}
            worker_idempotency_store(cur, worker_id, request, payload, response)
            return response


@app.post("/assignments/{assignment_id}/resume")
def resume_assignment(assignment_id: UUID, request: Request, worker_id: UUID = Depends(worker_id_from_token)):
    enforce_rate_limit(request, "write")
    payload={"assignment_id":str(assignment_id)}
    with db() as conn:
        with conn.cursor() as cur:
            replay=worker_idempotency_replay(cur, worker_id, request, payload)
            if replay is not None:
                return replay
            cur.execute(
                "select job_id,status from job_assignments where id=%s and worker_id=%s for update",
                (assignment_id,worker_id),
            )
            row=cur.fetchone()
            if not row: raise HTTPException(404,"Assignment not found")
            if row[1] not in ("ASSIGNED","RUNNING"):
                raise HTTPException(409, "Assignment is no longer resumable")
            cur.execute("select cursor_next from job_checkpoints where assignment_id=%s order by created_at desc,id desc limit 1",(assignment_id,))
            cp=cur.fetchone()
            response={"assignment_id":str(assignment_id),"status":row[1],"resume_cursor":cp[0] if cp else None}
            worker_idempotency_store(cur, worker_id, request, payload, response)
            return response


@app.get("/audit/explorer")
def audit_explorer(limit: int = 100):
    limit=max(1,min(limit,500))
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select id,event_type,entity_type,entity_id,account_id,worker_id,payload,event_hash,previous_hash,created_at from audit_events order by created_at desc,id desc limit %s",(limit,))
            rows=cur.fetchall()
    keys=["id","event_type","entity_type","entity_id","account_id","worker_id","payload","event_hash","previous_hash","created_at"]
    return {"events":[dict(zip(keys,r)) for r in rows]}



class ChallengeOfferCreate(BaseModel):
    challenge_id: str = Field(min_length=1, max_length=128)
    estimated_difficulty: float | None = Field(default=None, ge=0)
    estimated_seconds: int | None = Field(default=None, ge=0)
    required_capabilities: dict = Field(default_factory=dict)


@app.post("/creator/offers")
def create_offer(body: ChallengeOfferCreate, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload=body.model_dump()
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            cur.execute("select creator_account_id,creator_status from challenge_creators where challenge_id=%s",(body.challenge_id,))
            creator=cur.fetchone()
            if not creator or creator[0] != account_id:
                raise HTTPException(403,"Creator ownership required")
            if creator[1] != "APPROVED":
                raise HTTPException(409,"Creator must be approved before publishing")
            cur.execute("select reward_btc from challenge_registry where id=%s and status='OPEN + FUNDED'",(body.challenge_id,))
            ch=cur.fetchone()
            if not ch: raise HTTPException(409,"Challenge must be OPEN + FUNDED")
            oid=uuid4()
            cur.execute(
                "insert into challenge_offers(id,challenge_id,creator_account_id,reward_btc,estimated_difficulty,estimated_seconds,required_capabilities) "
                "values(%s,%s,%s,%s,%s,%s,%s::jsonb)",
                (oid,body.challenge_id,account_id,ch[0],body.estimated_difficulty,body.estimated_seconds,json.dumps(body.required_capabilities)),
            )
            record_audit_event(cur,"OFFER_CREATED","challenge_offer",oid,account_id,payload={"challenge_id":body.challenge_id})
            response={"offer_id":str(oid),"status":"DRAFT"}
            idempotency_store(cur, account_id, request, payload, response)
            return response

@app.post("/creator/offers/{offer_id}/publish")
def publish_offer(offer_id: UUID, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload={"offer_id":str(offer_id)}
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            cur.execute("update challenge_offers set status='PUBLISHED',published_at=now() where id=%s and creator_account_id=%s and status='DRAFT' returning challenge_id",(offer_id,account_id))
            row=cur.fetchone()
            if not row: raise HTTPException(409,"Offer cannot be published")
            record_audit_event(cur,"OFFER_PUBLISHED","challenge_offer",offer_id,account_id,payload={"challenge_id":row[0]})
            response={"offer_id":str(offer_id),"status":"PUBLISHED"}
            idempotency_store(cur, account_id, request, payload, response)
            return response

@app.post("/admin/creators/{challenge_id}/approve")
def approve_creator(challenge_id: str, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload={"challenge_id":challenge_id}
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            require_owner(cur, account_id)
            cur.execute("update challenge_creators set creator_status='APPROVED',approved_at=now() where challenge_id=%s and creator_status='PENDING' returning creator_account_id",(challenge_id,))
            row=cur.fetchone()
            if not row: raise HTTPException(409,"Creator is not pending")
            record_audit_event(cur,"CREATOR_APPROVED","challenge",challenge_id,account_id,payload={"creator_account_id":str(row[0]) if row[0] else None})
            response={"challenge_id":challenge_id,"status":"APPROVED"}
            idempotency_store(cur, account_id, request, payload, response)
            return response

@app.post("/admin/challenges/{challenge_id}/pause")
def pause_challenge(challenge_id: str, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload={"challenge_id":challenge_id}
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            require_owner(cur, account_id)
            cur.execute("update challenge_registry set status='OPEN + UNFUNDED' where id=%s and status='OPEN + FUNDED' returning id",(challenge_id,))
            if not cur.fetchone(): raise HTTPException(409,"Challenge is not currently OPEN + FUNDED")
            cur.execute("update challenge_offers set status='PAUSED' where challenge_id=%s and status='PUBLISHED'",(challenge_id,))
            record_audit_event(cur,"CHALLENGE_PAUSED","challenge",challenge_id,account_id)
            response={"challenge_id":challenge_id,"status":"PAUSED"}
            idempotency_store(cur, account_id, request, payload, response)
            return response

@app.get("/marketplace/challenges")
def marketplace():
    """Public read-only marketplace feed; starting work still requires authentication."""
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """select id,title,challenge_type,reward_btc,balance_btc,status,provenance,
                          verification,payout,source_adapter,live_checked_at,live_verification,
                          advertised_reward_btc,verified_balance_btc,funding_match,verification_stale,last_live_check_error
                   from challenge_registry
                   where status='OPEN + FUNDED'
                     and balance_btc > 0
                     and funding_match = true
                     and verification_stale = false
                     and coalesce((payout->>'permissionless'),'false')='true'
                     and coalesce((payout->>'automatic_chain_claim'),'false')='true'
                   order by balance_btc desc, updated_at desc, id asc
                   limit 100"""
            )
            keys=["challenge_id","title","challenge_type","reward_btc","balance_btc","status",
                  "provenance","verification","payout","source_adapter","live_checked_at","live_verification",
                  "advertised_reward_btc","verified_balance_btc","funding_match","verification_stale","last_live_check_error"]
            rows=[dict(zip(keys,x)) for x in cur.fetchall()]
            for row in rows:
                row["selected"]=False
            return {"challenges":rows,"offers":rows}


@app.get("/marketplace/challenges/{challenge_id}")
def marketplace_detail(challenge_id: str, account_id: UUID = Depends(account_id_from_auth)):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """select id,title,challenge_type,reward_btc,balance_btc,status,provenance,
                          verification,payout,source_adapter,live_checked_at,live_verification,
                          advertised_reward_btc,verified_balance_btc,funding_match,verification_stale,last_live_check_error
                   from challenge_registry where id=%s""",(challenge_id,))
            row=cur.fetchone()
            if not row: raise HTTPException(404,"Challenge not found")
            if row[5]!="OPEN + FUNDED" or row[4] <= 0 or row[14] is not True or row[15] is not False:
                raise HTTPException(409,"Challenge is not currently live and funded")
            keys=["challenge_id","title","challenge_type","reward_btc","balance_btc","status",
                  "provenance","verification","payout","source_adapter","live_checked_at","live_verification",
                  "advertised_reward_btc","verified_balance_btc","funding_match","verification_stale","last_live_check_error"]
            cur.execute("select 1 from challenge_selections where account_id=%s and challenge_id=%s",(account_id,challenge_id))
            selected=cur.fetchone() is not None
            return {**dict(zip(keys,row)),"selected":selected}


@app.post("/marketplace/challenges/{challenge_id}/run")
def run_marketplace_challenge(challenge_id: str, body: AssignmentCreate, request: Request,
                              account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request,"write")
    payload={"challenge_id":challenge_id,"worker_id":str(body.worker_id)}
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur,account_id,request,payload)
            if replay is not None: return replay
            cur.execute(
                """select id,status,balance_btc,payout from challenge_registry
                   where id=%s and status='OPEN + FUNDED' and balance_btc>0
                     and funding_match=true and verification_stale=false
                   for update""",(challenge_id,))
            challenge=cur.fetchone()
            if not challenge: raise HTTPException(409,"Challenge is not live, funded, or runnable")
            payout=challenge[3] or {}
            if payout.get("permissionless") is not True or payout.get("automatic_chain_claim") is not True:
                raise HTTPException(409,"Challenge payout mechanism is not independently verified")
            cur.execute("select id from workers where id=%s and account_id=%s and status='ACTIVE'",(body.worker_id,account_id))
            if not cur.fetchone(): raise HTTPException(400,"Selected worker is not active or does not belong to this account")
            cur.execute(
                "insert into challenge_selections(account_id,challenge_id) values(%s,%s) "
                "on conflict(account_id,challenge_id) do update set selected_at=now()",
                (account_id,challenge_id),
            )
            cur.execute(
                "select id,status from jobs where puzzle_id=%s and scope='public-reward-challenge' for update",
                (challenge_id,),
            )
            job=cur.fetchone()
            if job:
                job_id,job_status=job
                if job_status in ("COMPLETED","REJECTED","EXPIRED"):
                    cur.execute("update jobs set status='QUEUED',completed_at=null where id=%s",(job_id,))
            else:
                job_id=uuid4()
                cur.execute("insert into jobs(id,puzzle_id,scope,status) values(%s,%s,'public-reward-challenge','QUEUED')",(job_id,challenge_id))
            # Serialize puzzle switching per account so two simultaneous RUN requests
            # cannot both observe zero active assignments and create two active puzzles.
            cur.execute("select pg_advisory_xact_lock(hashtext(%s))",(str(account_id),))
            # One active puzzle per account. Switching puzzles pauses the previous assignment.
            cur.execute(
                """select a.id,a.job_id,a.worker_id,a.status,j.puzzle_id
                   from job_assignments a
                   join jobs j on j.id=a.job_id
                   join workers w on w.id=a.worker_id
                   where w.account_id=%s and a.status in ('ASSIGNED','RUNNING')
                   for update""",
                (account_id,),
            )
            active_for_account=cur.fetchall()
            for old_assignment_id,old_job_id,old_worker_id,old_status,old_puzzle_id in active_for_account:
                if old_puzzle_id == challenge_id and old_worker_id == body.worker_id:
                    response={"challenge_id":challenge_id,"job_id":str(old_job_id),
                              "assignment_id":str(old_assignment_id),"worker_id":str(body.worker_id),
                              "status":old_status}
                    idempotency_store(cur,account_id,request,payload,response)
                    return response
                # Switching puzzles must also stop the previous managed solver.
                # Releasing the DB row alone is not enough to stop its hashing thread.
                _stop_managed_solver(old_assignment_id)
                cur.execute(
                    "update job_assignments set status='RELEASED',last_heartbeat_at=null where id=%s and status in ('ASSIGNED','RUNNING')",
                    (old_assignment_id,),
                )
                cur.execute(
                    """update jobs set status='QUEUED',completed_at=null
                       where id=%s and status in ('QUEUED','RUNNING')
                         and not exists (
                           select 1 from job_assignments
                           where job_id=%s and status in ('ASSIGNED','RUNNING')
                         )""",
                    (old_job_id,old_job_id),
                )
                record_audit_event(
                    cur,"RELEASED","assignment",old_assignment_id,account_id,old_worker_id,
                    {"job_id":str(old_job_id),"puzzle_id":old_puzzle_id,
                     "reason":"account_switched_puzzle","next_challenge_id":challenge_id},
                )

            # Reuse a paused assignment for the same worker/challenge.
            cur.execute(
                """select a.id,a.job_id from job_assignments a
                   join jobs j on j.id=a.job_id
                   where a.worker_id=%s and j.puzzle_id=%s and a.status='RELEASED'
                   order by a.assigned_at desc limit 1 for update""",
                (body.worker_id,challenge_id),
            )
            paused=cur.fetchone()
            if paused:
                aid,job_id=paused
                capacity=economic_capacity(cur,job_id)
                if not capacity["allowed"]: raise HTTPException(429, allocation_capacity_error(capacity["reason"]))
                cur.execute(
                    "update job_assignments set status='ASSIGNED',started_at=null,last_heartbeat_at=null,completed_at=null,expired_at=null where id=%s",
                    (aid,),
                )
            else:
                capacity=economic_capacity(cur,job_id)
                if not capacity["allowed"]: raise HTTPException(429,f"Allocation paused: {capacity['reason']}")
                aid=uuid4()
                cur.execute("insert into job_assignments(id,job_id,worker_id,status) values(%s,%s,%s,'ASSIGNED')",(aid,job_id,body.worker_id))
            record_audit_event(cur,"CHALLENGE_SELECTED","challenge",challenge_id,account_id=account_id,worker_id=body.worker_id,
                               payload={"job_id":str(job_id),"assignment_id":str(aid),"selection":"marketplace"})
            response={"challenge_id":challenge_id,"job_id":str(job_id),"assignment_id":str(aid),"worker_id":str(body.worker_id),"status":"ASSIGNED"}
            idempotency_store(cur,account_id,request,payload,response)
            # Start the managed solver only after this transaction commits.
            managed_solver_start=(aid,job_id,body.worker_id)

    _start_managed_solver(*managed_solver_start)
    return response


@app.post("/creator/challenges")
def creator_challenge(body: CreatorChallenge, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload=body.model_dump()
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            cur.execute("select id from challenge_registry where id=%s",(body.challenge_id,))
            if not cur.fetchone(): raise HTTPException(404,"Challenge not found")
            cur.execute(
                "insert into challenge_creators(challenge_id,creator_account_id,terms) values(%s,%s,%s::jsonb) "
                "on conflict(challenge_id) do update set creator_account_id=excluded.creator_account_id,terms=excluded.terms",
                (body.challenge_id,account_id,json.dumps(body.terms)),
            )
            record_audit_event(cur,"CREATOR_REGISTERED","challenge",body.challenge_id,account_id,payload={"terms":body.terms})
            response={"challenge_id":body.challenge_id,"creator_status":"PENDING"}
            idempotency_store(cur, account_id, request, payload, response)
            return response

@app.post("/jobs/{job_id}/schedule")
def schedule_job(job_id: UUID, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload={"job_id":str(job_id)}
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            cur.execute("""
                select j.id,j.puzzle_id,j.status,c.challenge_type
                from jobs j join challenge_registry c on c.id=j.puzzle_id
                where j.id=%s and j.status='QUEUED' and c.status='OPEN + FUNDED'
                for update
            """,(job_id,))
            job=cur.fetchone()
            if not job: raise HTTPException(409,"Job is not schedulable")
            cur.execute("""
                select w.id,w.last_seen_at,coalesce(wc.cpu_threads,1),coalesce(wc.adapter_types,'[]'::jsonb)
                from workers w
                left join worker_capabilities wc on wc.worker_id=w.id
                where w.status='ACTIVE'
                order by (w.last_seen_at is null),w.last_seen_at desc
                limit 100
            """)
            candidates=cur.fetchall()
            if not candidates: raise HTTPException(409,"No active workers available")
            ranked=[]
            for wid,last_seen,threads,adapters in candidates:
                cur.execute(
                    "select "
                    "count(*) filter (where result_status in ('TESTED','VERIFIED','REJECTED')), "
                    "count(*) filter (where result_status='VERIFIED'), "
                    "count(*) filter (where result_status='REJECTED') "
                    "from work_claims where worker_id=%s and finished_at > now() - interval '30 days'",
                    (wid,),
                )
                claim_count,verified_count,rejected_count=cur.fetchone()
                cur.execute(
                    "select count(*) filter (where status='COMPLETED'), "
                    "count(*) filter (where status='EXPIRED'), "
                    "coalesce(sum(verified_seconds),0) "
                    "from job_assignments where worker_id=%s and assigned_at > now() - interval '30 days'",
                    (wid,),
                )
                completed_count,stale_count,total_seconds=cur.fetchone()
                cur.execute(
                    "select count(*) from security_events "
                    "where worker_id=%s and event_type='DUPLICATE_CLAIM' "
                    "and created_at > now() - interval '30 days'",
                    (wid,),
                )
                duplicate_count=cur.fetchone()[0]
                rep=reputation_score(
                    claim_count,verified_count,rejected_count+duplicate_count,stale_count,
                    completed_count,total_seconds,
                )
                score=capability_score({"id":wid,"cpu_threads":threads,"adapter_types":adapters or []},{"adapter_types":[job[3]]})
                if score>0:
                    ranked.append({
                        "id":wid,
                        "score":score*(float(rep)/100.0),
                        "reputation":rep,
                        "security_flags":security_flags(claim_count,duplicate_count,rejected_count,stale_count),
                    })
            if not ranked: raise HTTPException(409,"No compatible workers available")
            ranked.sort(key=lambda x:(x["score"],str(x["id"])),reverse=True)
            selected=ranked[0]
            cur.execute(
                "insert into scheduler_decisions(id,job_id,worker_id,score,reason) values(%s,%s,%s,%s,%s::jsonb)",
                (uuid4(),job_id,selected["id"],selected["score"],json.dumps({"strategy":"capability+reputation"})),
            )
            record_audit_event(cur,"SCHEDULER_DECISION","job",job_id,account_id,selected["id"],payload={"score":selected["score"],"reputation":selected["reputation"],"security_flags":selected["security_flags"]})
            response={"job_id":str(job_id),"selected_worker_id":str(selected["id"]),"score":selected["score"]}
            idempotency_store(cur, account_id, request, payload, response)
            return response

@app.get("/network")
def network():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from workers where status='ACTIVE'")
            workers=cur.fetchone()[0]
            cur.execute("select count(*) from workers where status='ACTIVE' and last_seen_at > now() - interval '2 minutes'")
            online=cur.fetchone()[0]
            cur.execute("select count(*) from jobs where status in ('QUEUED','RUNNING')")
            active_jobs=cur.fetchone()[0]
            cur.execute("select coalesce(sum(seconds_verified),0) from worker_hours")
            seconds=cur.fetchone()[0]
            cur.execute("select count(*) from jobs where status='VERIFIED'")
            verified=cur.fetchone()[0]
    return {
        "workers": workers,
        "online_workers": online,
        "active_jobs": active_jobs,
        "contribution_hours": round(float(seconds)/3600, 2),
        "verified_jobs": verified,
        "source": "postgresql",
    }


@app.get("/reputation")
def reputation(account_id: UUID = Depends(account_id_from_auth)):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                select
                  count(*) filter (where c.result_status in ('TESTED','VERIFIED','REJECTED')),
                  count(*) filter (where c.result_status='VERIFIED'),
                  count(*) filter (where c.result_status='REJECTED'),
                  coalesce(sum(c.cpu_seconds),0)
                from work_claims c join workers w on w.id=c.worker_id
                where w.account_id=%s and c.finished_at > now() - interval '30 days'
            """,(account_id,))
            claim_count,verified,rejected,cpu=cur.fetchone()
            cur.execute("""
                select
                  count(*) filter (where a.status='COMPLETED'),
                  count(*) filter (where a.status='EXPIRED'),
                  coalesce(sum(a.verified_seconds),0)
                from job_assignments a join workers w on w.id=a.worker_id
                where w.account_id=%s and a.assigned_at > now() - interval '30 days'
            """,(account_id,))
            completed,stale,seconds=cur.fetchone()
            cur.execute("""
                select count(*) from security_events s
                join workers w on w.id=s.worker_id
                where w.account_id=%s and s.event_type='DUPLICATE_CLAIM'
                and s.created_at > now() - interval '30 days'
            """,(account_id,))
            duplicates=cur.fetchone()[0]
    score=reputation_score(claim_count,verified,rejected+duplicates,stale,completed,seconds)
    flags=security_flags(claim_count,duplicates,rejected,stale)
    return {
        "verified_claims":verified,
        "rejected_claims":rejected,
        "duplicate_claims":duplicates,
        "completed_assignments":completed,
        "stale_assignments":stale,
        "contributed_worker_seconds":seconds,
        "cpu_seconds":cpu,
        "reliability_score":score,
        "security_flags":flags,
        "window_days":30,
    }


@app.get("/health")
def health():
    return {"ok": True, "service": "satoshi-hunt-api", "version": "0.1.1", "custody": "non-custodial"}


@app.get("/ready")
def ready():
    if not DATABASE_URL:
        raise HTTPException(503, "DATABASE_URL is not configured")
    try:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
                cur.fetchone()
    except Exception as exc:
        logging.error("Database readiness check failed: %s", type(exc).__name__)
        raise HTTPException(503, "Database unavailable")
    redis_ok = True
    if _redis:
        try:
            _redis.ping()
        except Exception:
            redis_ok = False
    return {"ready": True, "database": True, "redis": redis_ok, "rate_limit_mode": "redis" if _redis and redis_ok else "fallback"}



@app.post("/auth/register")
def register_account(body: RegisterRequest, request: Request):
    enforce_rate_limit(request, "auth_request")
    email = body.email.lower().strip()
    password_hash = hash_password(body.password)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select id,password_hash from accounts where email=%s for update", (email,))
            row = cur.fetchone()
            if row:
                if row[1]:
                    raise HTTPException(409, "Account already exists")
                cur.execute("update accounts set password_hash=%s where id=%s", (password_hash, row[0]))
                account_id = row[0]
            else:
                account_id = uuid4()
                cur.execute("insert into accounts(id,email,password_hash) values(%s,%s,%s)", (account_id,email,password_hash))
    return {"session": issue_session(account_id), "expires_in": SESSION_TTL}


@app.post("/auth/login")
def login_account(body: LoginRequest, request: Request):
    enforce_rate_limit(request, "auth_verify")
    email = body.email.lower().strip()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select id,password_hash from accounts where email=%s", (email,))
            row = cur.fetchone()
    if not row or not row[1] or not verify_password(body.password, row[1]):
        raise HTTPException(401, "Invalid email or password")
    return {"session": issue_session(row[0]), "expires_in": SESSION_TTL}


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



@app.get("/account/rewards")
def account_rewards(account_id: UUID = Depends(account_id_from_auth)):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select coalesce(available_btc,0) from reward_balances where account_id=%s",
                (account_id,),
            )
            row = cur.fetchone()
            available = Decimal(str(row[0] if row else 0))
            cur.execute(
                "select id,amount_btc,payout_address,status,external_reference,created_at,processed_at "
                "from withdrawal_requests where account_id=%s order by created_at desc limit 10",
                (account_id,),
            )
            withdrawals = [
                {
                    "id": str(x[0]),
                    "amount_btc": float(x[1]),
                    "payout_address": x[2],
                    "status": x[3],
                    "external_reference": x[4],
                    "created_at": x[5],
                    "processed_at": x[6],
                }
                for x in cur.fetchall()
            ]
    return {"available_btc": float(available), "withdrawals": withdrawals}


@app.put("/account/payout-address")
def update_account_payout_address(payload: dict, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    return _update_account_payout_address_sync(request, account_id, payload)


def _update_account_payout_address_sync(request: Request, account_id: UUID, payload):
    # Kept as a small helper so the account route remains compatible with the
    # existing synchronous DB layer.
    address = str(payload.get("btc_payout_address", "")).strip()
    if not valid_btc_mainnet_address(address):
        raise HTTPException(422, "A valid Bitcoin mainnet payout address is required")
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "update accounts set btc_payout_address=%s where id=%s returning id",
                (address, account_id),
            )
            if not cur.fetchone():
                raise HTTPException(404, "Account not found")
            record_audit_event(
                cur, "PAYOUT_ADDRESS_UPDATED", "account", account_id,
                account_id=account_id, payload={"address_present": True},
            )
    return {"status": "SAVED", "btc_payout_address": address}


@app.post("/account/withdrawals")
def create_account_withdrawal(payload: dict, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    with db() as conn:
        with conn.cursor() as cur:
            replay = idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay

            cur.execute(
                "select btc_payout_address from accounts where id=%s for update",
                (account_id,),
            )
            account = cur.fetchone()
            if not account:
                raise HTTPException(404, "Account not found")
            payout_address = (account[0] or "").strip()
            if not payout_address:
                raise HTTPException(409, "Save a valid BTC payout address before withdrawing")

            try:
                requested = Decimal(str(payload.get("amount_btc")))
            except Exception:
                raise HTTPException(422, "Withdrawal amount must be a valid BTC amount")
            if requested <= 0:
                raise HTTPException(422, "Withdrawal amount must be greater than zero")
            if requested > MAX_SINGLE_PAYOUT_BTC:
                raise HTTPException(409, f"Withdrawal exceeds the single-payout limit of {MAX_SINGLE_PAYOUT_BTC} BTC")

            cur.execute(
                "select coalesce(available_btc,0) from reward_balances where account_id=%s for update",
                (account_id,),
            )
            row = cur.fetchone()
            available = Decimal(str(row[0] if row else 0))
            if available <= 0 or requested > available:
                raise HTTPException(409, "There is no available reward balance to withdraw at this time")

            treasury_available = treasury_available_btc(cur)
            if treasury_available < requested:
                raise HTTPException(409, "Treasury does not currently have enough available BTC for this withdrawal")

            cur.execute(
                "update reward_balances set available_btc=available_btc-%s,updated_at=now() "
                "where account_id=%s and available_btc >= %s",
                (requested, account_id, requested),
            )
            if cur.rowcount != 1:
                raise HTTPException(409, "Reward balance changed. Please refresh and try again.")

            wid = uuid4()
            cur.execute(
                "insert into withdrawal_requests(id,account_id,amount_btc,payout_address,status) "
                "values(%s,%s,%s,%s,'QUEUED')",
                (wid, account_id, requested, payout_address),
            )
            cur.execute(
                "update treasury_accounting set reserved_btc=reserved_btc+%s,updated_at=now() where id=%s",
                (requested, TREASURY_WALLET_ID),
            )
            treasury_ledger(
                cur, "USER_WITHDRAWAL_RESERVED", requested, "WITHDRAWAL", wid,
                account_id=account_id, destination_btc_address=payout_address,
            )
            record_audit_event(
                cur, "WITHDRAWAL_QUEUED", "withdrawal", wid,
                account_id=account_id,
                payload={"amount_btc": str(requested), "payout_address_present": True},
            )
            response = {
                "status": "QUEUED",
                "withdrawal_id": str(wid),
                "amount_btc": float(requested),
                "payout_address": payout_address,
            }
            idempotency_store(cur, account_id, request, payload, response)
            return response


def require_owner(cur, account_id: UUID):
    if not OWNER_EMAIL:
        raise HTTPException(503, "OWNER_EMAIL is not configured")
    cur.execute("select email from accounts where id=%s", (account_id,))
    row = cur.fetchone()
    if not row or row[0].lower() != OWNER_EMAIL:
        raise HTTPException(403, "Owner authorization required")


def require_payout_worker(request: Request):
    if not PAYOUT_WORKER_TOKEN:
        raise HTTPException(503, "Payout worker is not configured")
    supplied = request.headers.get("X-Payout-Worker-Token", "").strip()
    if not supplied or not secrets.compare_digest(supplied, PAYOUT_WORKER_TOKEN):
        raise HTTPException(401, "Payout worker authorization required")


def idempotency_key(request: Request):
    value = request.headers.get("Idempotency-Key", "").strip()
    if value and len(value) <= 128:
        return value
    return None




def idempotency_fingerprint(request: Request, payload) -> str:
    canonical = json.dumps({"method": request.method, "path": request.url.path, "payload": payload}, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(canonical).hexdigest()


def idempotency_replay(cur, account_id: UUID, request: Request, payload):
    key = idempotency_key(request)
    if not key:
        return None
    fingerprint = idempotency_fingerprint(request, payload)
    cur.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"satoshi-hunt:idempotency:{account_id}:{key}",))
    cur.execute("select request_hash,response_json from idempotency_records where account_id=%s and idempotency_key=%s", (account_id, key))
    row = cur.fetchone()
    if not row:
        return None
    if row[0] != fingerprint:
        raise HTTPException(409, "Idempotency-Key was already used with a different request")
    return row[1]


def idempotency_store(cur, account_id: UUID, request: Request, payload, response):
    key = idempotency_key(request)
    if not key:
        return
    fingerprint = idempotency_fingerprint(request, payload)
    cur.execute("insert into idempotency_records(account_id,idempotency_key,request_hash,response_json) values(%s,%s,%s,%s::jsonb) on conflict (account_id,idempotency_key) do nothing", (account_id, key, fingerprint, json.dumps(response, default=str)))

def worker_token():
    return secrets.token_urlsafe(32)


def worker_owned(cur, worker_id: UUID, account_id: UUID, active_only=True):
    if active_only:
        cur.execute("select id from workers where id=%s and account_id=%s and status='ACTIVE'", (worker_id, account_id))
    else:
        cur.execute("select id from workers where id=%s and account_id=%s", (worker_id, account_id))
    return cur.fetchone()


@app.post("/workers")
def create_worker(body: WorkerCreate, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    wid = uuid4()
    worker_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(worker_token.encode()).hexdigest()
    with db() as conn:
        with conn.cursor() as cur:
            payload = body.model_dump(mode="json")
            replay = idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            cur.execute("insert into workers(id,account_id,label,token_hash) values(%s,%s,%s,%s)", (wid, account_id, body.label, token_hash))
            response = {"id": str(wid), "label": body.label, "status": "ACTIVE", "worker_token": worker_token}
            idempotency_store(cur, account_id, request, payload, response)
    return response


@app.post("/workers/{worker_id}/rotate")
def rotate_worker(worker_id: UUID, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    token = worker_token()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with db() as conn:
        with conn.cursor() as cur:
            if not worker_owned(cur, worker_id, account_id, active_only=True):
                raise HTTPException(404, "Worker not found")
            payload = {"worker_id": str(worker_id)}
            replay = idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            cur.execute("update workers set token_hash=%s,last_seen_at=now() where id=%s and status='ACTIVE'", (token_hash,worker_id))
            if cur.rowcount != 1: raise HTTPException(409, "Worker is not active")
            record_audit_event(cur,"WORKER_TOKEN_ROTATED","worker",worker_id,account_id,worker_id,payload={"credential_storage":"digest_only"})
            response = {"worker_id":str(worker_id),"worker_token":token,"storage":"memory_only"}
            idempotency_store(cur, account_id, request, payload, response)
    return response


@app.post("/workers/{worker_id}/revoke")
def revoke_worker(worker_id: UUID, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    with db() as conn:
        with conn.cursor() as cur:
            payload = {"worker_id": str(worker_id)}
            replay = idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            cur.execute("select id from workers where id=%s and account_id=%s for update", (worker_id, account_id))
            row=cur.fetchone()
            if not row:
                raise HTTPException(404, "Worker not found")
            cur.execute("update workers set status='REVOKED',token_hash=null where id=%s and status <> 'REVOKED'", (worker_id,))
            cur.execute(
                "update job_assignments set status='EXPIRED',expired_at=now() "
                "where worker_id=%s and status in ('ASSIGNED','RUNNING') returning id,job_id",
                (worker_id,),
            )
            expired=cur.fetchall()
            for assignment_id,job_id in expired:
                cur.execute(
                    "update jobs set status='QUEUED',completed_at=null "
                    "where id=%s and status in ('RUNNING','QUEUED') "
                    "and not exists (select 1 from job_assignments where job_id=%s and status in ('ASSIGNED','RUNNING'))",
                    (job_id,job_id),
                )
                record_audit_event(
                    cur,"EXPIRED","assignment",assignment_id,account_id,worker_id,
                    {"job_id":str(job_id),"reason":"worker_revoked"},
                )
            record_audit_event(cur,"REVOKED","worker",worker_id,account_id,worker_id,{"reason":"account_requested","expired_assignments":len(expired)})
            response={"ok":True,"worker_id":str(worker_id),"status":"REVOKED","expired_assignments":len(expired)}
            idempotency_store(cur, account_id, request, payload, response)
    return response


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
    payload={"worker_id":str(worker_id)}
    with db() as conn:
        with conn.cursor() as cur:
            if token_worker_id != worker_id:
                raise HTTPException(403, "Worker token does not match worker")
            replay=worker_idempotency_replay(cur, token_worker_id, request, payload)
            if replay is not None:
                return replay
            cur.execute("select id from workers where id=%s and status='ACTIVE'", (worker_id,))
            if not cur.fetchone():
                raise HTTPException(404, "Worker not found")
            cur.execute("update workers set last_seen_at=now() where id=%s", (worker_id,))
            response={"ok": True, "worker_id": str(worker_id)}
            worker_idempotency_store(cur, token_worker_id, request, payload, response)
            return response


@app.get("/jobs")
def list_jobs(account_id: UUID = Depends(account_id_from_auth)):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select j.id,j.puzzle_id,j.status,j.created_at,j.completed_at,a.id,a.worker_id,a.status,a.assigned_at,a.started_at,a.completed_at,a.last_heartbeat_at,a.verified_seconds from jobs j left join lateral (select a.id,a.worker_id,a.status,a.assigned_at,a.started_at,a.completed_at,a.last_heartbeat_at,a.verified_seconds from job_assignments a join workers w on w.id=a.worker_id where a.job_id=j.id and w.account_id=%s order by a.assigned_at desc limit 1) a on true where j.scope='public-reward-challenge' order by j.created_at desc limit 50", (account_id,))
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


@app.post("/internal/challenges")
def ingest_challenge(body: ChallengeIngest, request: Request, x_challenge_ingestion_key: str = Header(default="")):
    enforce_rate_limit(request, "write")
    if not CHALLENGE_INGESTION_KEY:
        raise HTTPException(503, "Challenge ingestion is not configured")
    if not secrets.compare_digest(x_challenge_ingestion_key, CHALLENGE_INGESTION_KEY):
        raise HTTPException(401, "Invalid challenge ingestion credential")
    if body.status != "OPEN + FUNDED" or body.balance_btc <= 0:
        raise HTTPException(400, "Only OPEN + FUNDED challenges may enter the solver queue")
    if body.rules != "public-reward-challenge" or not body.provenance or not body.verification:
        raise HTTPException(400, "Challenge provenance and verification metadata are required")
    required_provenance = ("url", "source_id", "checked_at")
    required_verification = ("method", "source_id", "checked_at", "fingerprint")
    if any(not body.provenance.get(key) for key in required_provenance):
        raise HTTPException(400, "Complete provenance metadata is required")
    if any(not body.verification.get(key) for key in required_verification):
        raise HTTPException(400, "Complete verification metadata is required")
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into challenge_registry(id,title,challenge_type,reward_btc,balance_btc,status,rules,provenance,verification) "
                "values(%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "on conflict (id) do update set title=excluded.title,challenge_type=excluded.challenge_type,"
                "reward_btc=excluded.reward_btc,balance_btc=excluded.balance_btc,status=excluded.status,rules=excluded.rules,"
                "provenance=excluded.provenance,verification=excluded.verification,updated_at=now()",
                (body.id,body.title,body.challenge_type,body.reward_btc,body.balance_btc,body.status,body.rules,body.provenance,body.verification),
            )
            cur.execute(
                "select id from jobs where puzzle_id=%s and scope='public-reward-challenge' "
                "order by created_at desc limit 1 for update",
                (body.id,),
            )
            existing = cur.fetchone()
            if existing:
                job_id = existing[0]
            else:
                job_id=uuid4()
                cur.execute(
                    "insert into jobs(id,puzzle_id,scope,status) values(%s,%s,'public-reward-challenge','QUEUED') "
                    "on conflict (puzzle_id,scope) do nothing returning id",
                    (job_id,body.id),
                )
                inserted = cur.fetchone()
                if inserted:
                    job_id = inserted[0]
                    record_audit_event(cur,"CHALLENGE_INGESTED","challenge",body.id,payload={"job_id":str(job_id),"verification_fingerprint":body.verification.get("fingerprint")})
                else:
                    cur.execute(
                        "select id from jobs where puzzle_id=%s and scope='public-reward-challenge' "
                        "for update",
                        (body.id,),
                    )
                    job_id = cur.fetchone()[0]
    return {"challenge_id":body.id,"job_id":str(job_id),"status":"QUEUED"}




@app.get("/admin/workers/live")
def admin_live_workers(account_id: UUID = Depends(account_id_from_auth)):
    """Owner-only operational view of workers actually leased to active assignments."""
    with db() as conn:
        with conn.cursor() as cur:
            require_owner(cur, account_id)
            cur.execute(
                """
                select
                    a.id,
                    a.job_id,
                    a.worker_id,
                    w.account_id,
                    w.label,
                    a.status,
                    a.assigned_at,
                    a.started_at,
                    a.last_heartbeat_at,
                    extract(epoch from (now() - a.last_heartbeat_at)) as heartbeat_age_seconds,
                    j.puzzle_id,
                    j.status as job_status
                from job_assignments a
                join workers w on w.id=a.worker_id
                join jobs j on j.id=a.job_id
                where a.status='RUNNING'
                order by a.started_at asc nulls last
                """
            )
            rows=cur.fetchall()
    workers=[]
    for r in rows:
        heartbeat_age = None if r[9] is None else float(r[9])
        workers.append({
            "assignment_id": str(r[0]),
            "job_id": str(r[1]),
            "worker_id": str(r[2]),
            "account_id": str(r[3]),
            "worker_label": r[4],
            "assignment_status": r[5],
            "assigned_at": r[6],
            "started_at": r[7],
            "last_heartbeat_at": r[8],
            "heartbeat_age_seconds": heartbeat_age,
            "heartbeat_healthy": heartbeat_age is not None and heartbeat_age <= 45,
            "puzzle_id": r[10],
            "job_status": r[11],
        })
    return {
        "active_workers": sum(1 for x in workers if x["heartbeat_healthy"]),
        "running_assignments": len(workers),
        "workers": workers,
        "checked_at": datetime.now(timezone.utc),
    }


@app.get("/admin/rewards")
def admin_rewards(account_id: UUID = Depends(account_id_from_auth)):
    with db() as conn:
        with conn.cursor() as cur:
            require_owner(cur, account_id)
            cur.execute(
                "select id,account_id,puzzle_id,gross_reward_btc,worker_share_btc,platform_fee_btc,settlement_status,source_claim_id,created_at,approved_at,settled_at "
                "from reward_events order by created_at desc limit 100"
            )
            return {"rewards":[dict(zip(["id","account_id","puzzle_id","gross_reward_btc","worker_share_btc","platform_fee_btc","settlement_status","source_claim_id","created_at","approved_at","settled_at"],r)) for r in cur.fetchall()]}


@app.post("/admin/rewards/{reward_id}/approve")
def approve_reward(reward_id: UUID, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload={"reward_id":str(reward_id)}
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            require_owner(cur, account_id)
            cur.execute("update reward_events set settlement_status='APPROVED',approved_at=now() where id=%s and settlement_status='REVIEW' returning puzzle_id,account_id", (reward_id,))
            row=cur.fetchone()
            if not row: raise HTTPException(409, "Reward is not in REVIEW")
            record_audit_event(cur,"REWARD_APPROVED","reward_event",reward_id,account_id,payload={"puzzle_id":row[0],"beneficiary_account":str(row[1])})
            response={"status":"APPROVED","reward_id":str(reward_id)}
            idempotency_store(cur, account_id, request, payload, response)
            return response

@app.post("/admin/rewards/{reward_id}/void")
def void_reward(reward_id: UUID, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload={"reward_id":str(reward_id)}
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            require_owner(cur, account_id)
            cur.execute("update reward_events set settlement_status='VOID' where id=%s and settlement_status in ('REVIEW','APPROVED') returning puzzle_id", (reward_id,))
            row=cur.fetchone()
            if not row: raise HTTPException(409, "Reward cannot be voided from its current state")
            record_audit_event(cur,"REWARD_VOID","reward_event",reward_id,account_id,payload={"puzzle_id":row[0]})
            response={"status":"VOID","reward_id":str(reward_id)}
            idempotency_store(cur, account_id, request, payload, response)
            return response

@app.post("/admin/rewards/{reward_id}/settle")
def settle_reward(reward_id: UUID, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload={"reward_id":str(reward_id)}
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            require_owner(cur, account_id)
            cur.execute("update reward_events set settlement_status='SETTLED',settled_at=now() where id=%s and settlement_status='APPROVED' returning puzzle_id,account_id,worker_share_btc,platform_fee_btc", (reward_id,))
            row=cur.fetchone()
            if not row: raise HTTPException(409, "Reward must be APPROVED before settlement")
            record_audit_event(cur,"REWARD_SETTLED","reward_event",reward_id,account_id,payload={"puzzle_id":row[0],"beneficiary_account":str(row[1]),"custody":"none"})
            response={"status":"SETTLED","reward_id":str(reward_id),"custody":"non-custodial"}
            idempotency_store(cur, account_id, request, payload, response)
            return response

@app.get("/admin/community")
def admin_community(account_id: UUID = Depends(account_id_from_auth)):
    with db() as conn:
        with conn.cursor() as cur:
            require_owner(cur, account_id)
            cur.execute("select id,source_reward_event_id,amount_btc,status,created_at,approved_at,distributed_at from community_allocations order by created_at desc limit 100")
            return {"allocations":[dict(zip(["id","source_reward_event_id","amount_btc","status","created_at","approved_at","distributed_at"],r)) for r in cur.fetchall()]}


@app.post("/admin/community")
def create_community_allocation(source_reward_event_id: UUID, amount_btc: float, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload={"source_reward_event_id":str(source_reward_event_id),"amount_btc":amount_btc}
    if amount_btc <= 0: raise HTTPException(400, "amount_btc must be positive")
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            require_owner(cur, account_id)
            cur.execute("select platform_fee_btc,account_id,puzzle_id,settlement_status from reward_events where id=%s for update", (source_reward_event_id,))
            row=cur.fetchone()
            if not row or row[3] != "SETTLED": raise HTTPException(409, "Source reward must be SETTLED")
            cur.execute("select coalesce(sum(amount_btc),0) from community_allocations where source_reward_event_id=%s and status <> 'CANCELLED'", (source_reward_event_id,))
            allocated = cur.fetchone()[0]
            remaining = row[0] - allocated
            if Decimal(str(amount_btc)) > remaining:
                raise HTTPException(400, "Allocation exceeds the remaining platform fee for this reward event")
            cur.execute("insert into community_allocations(id,source_reward_event_id,amount_btc) values(%s,%s,%s) returning id", (uuid4(),source_reward_event_id,amount_btc))
            alloc=cur.fetchone()[0]
            record_audit_event(cur,"COMMUNITY_ALLOCATION_CREATED","community_allocation",alloc,account_id,payload={"source_reward_event":str(source_reward_event_id),"amount_btc":amount_btc})
            response={"id":str(alloc),"status":"MANUAL_REVIEW"}
            idempotency_store(cur, account_id, request, payload, response)
            return response

@app.post("/admin/community/{allocation_id}/approve")
def approve_community(allocation_id: UUID, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload={"allocation_id":str(allocation_id)}
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            require_owner(cur, account_id)
            cur.execute("update community_allocations set status='APPROVED',approved_at=now() where id=%s and status='MANUAL_REVIEW' returning amount_btc", (allocation_id,))
            row=cur.fetchone()
            if not row: raise HTTPException(409, "Allocation is not in MANUAL_REVIEW")
            record_audit_event(cur,"COMMUNITY_ALLOCATION_APPROVED","community_allocation",allocation_id,account_id,payload={"amount_btc":row[0]})
            response={"status":"APPROVED","id":str(allocation_id)}
            idempotency_store(cur, account_id, request, payload, response)
            return response

@app.post("/admin/community/{allocation_id}/distributed")
def distribute_community(allocation_id: UUID, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload={"allocation_id":str(allocation_id)}
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            require_owner(cur, account_id)
            cur.execute("update community_allocations set status='DISTRIBUTED',distributed_at=now() where id=%s and status='APPROVED' returning amount_btc", (allocation_id,))
            row=cur.fetchone()
            if not row: raise HTTPException(409, "Allocation must be APPROVED before distribution")
            record_audit_event(cur,"COMMUNITY_ALLOCATION_DISTRIBUTED","community_allocation",allocation_id,account_id,payload={"amount_btc":row[0],"custody":"none"})
            response={"status":"DISTRIBUTED","id":str(allocation_id),"custody":"non-custodial"}
            idempotency_store(cur, account_id, request, payload, response)
            return response

@app.post("/jobs")
def create_job(body: JobCreate, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    raise HTTPException(403, "Jobs are created only by the verified challenge-ingestion pipeline.")



def allocation_capacity_error(reason: str) -> str:
    messages = {
        "THIS_PUZZLE_IS_ALREADY_RUNNING": "This puzzle is already running on another worker. Choose another live puzzle.",
        "NETWORK_ASSIGNMENT_CAP": "The network is temporarily at its worker capacity. Please try again shortly.",
        "DAILY_WORKER_HOUR_CAP": "The network has reached its daily worker capacity. Please try again later.",
        "CHALLENGE_NOT_FUNDED": "This puzzle is no longer funded or runnable.",
    }
    return messages.get(reason, f"Allocation is temporarily unavailable: {reason}")


def economic_capacity(cur, job_id: UUID):
    # Serialize allocation decisions so concurrent requests cannot overshoot
    # the global active-assignment ceiling.
    cur.execute("select pg_advisory_xact_lock(93218471)")
    cur.execute("select count(*) from job_assignments where status in ('ASSIGNED','RUNNING')")
    active_assignments = cur.fetchone()[0]
    if active_assignments >= MAX_ACTIVE_ASSIGNMENTS:
        return {"allowed": False, "reason": "NETWORK_ASSIGNMENT_CAP"}
    # A single puzzle may be solved by many workers concurrently.
    # The global network cap remains the safety valve; there is intentionally
    # no per-puzzle assignment cap.
    cur.execute("select coalesce(sum(seconds_verified),0) from worker_hours where period_start=current_date")
    daily_hours = int(cur.fetchone()[0] or 0) / 3600
    if daily_hours >= MAX_NETWORK_WORKER_HOURS_PER_DAY:
        return {"allowed": False, "reason": "DAILY_WORKER_HOUR_CAP"}
    cur.execute("select c.balance_btc,c.status from jobs j join challenge_registry c on c.id=j.puzzle_id where j.id=%s for update", (job_id,))
    challenge = cur.fetchone()
    if not challenge or challenge[1] != "OPEN + FUNDED" or challenge[0] <= 0:
        return {"allowed": False, "reason": "CHALLENGE_NOT_FUNDED"}
    return {"allowed": True}


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
            capacity = economic_capacity(cur, job_id)
            if not capacity["allowed"]:
                raise HTTPException(429, allocation_capacity_error(capacity["reason"]))
            cur.execute(
                "select id from workers where id=%s and account_id=%s and status='ACTIVE' for update",
                (body.worker_id, account_id),
            )
            if not cur.fetchone():
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
        "and coalesce(last_heartbeat_at,assigned_at) < %s "
        "returning id,job_id,worker_id",
        (cutoff,),
    )
    for assignment_id,job_id,worker_id in cur.fetchall():
        # A managed solver can outlive the HTTP request that started it. Stop
        # that process too when the database assignment expires, otherwise the
        # UI may show EXPIRED while the server keeps consuming CPU.
        _stop_managed_solver(assignment_id)
        cur.execute(
            """update jobs set status='QUEUED',completed_at=null
               where id=%s and status in ('RUNNING','QUEUED')
                 and not exists (
                   select 1 from job_assignments
                   where job_id=%s and status in ('ASSIGNED','RUNNING')
                 )""",
            (job_id,job_id),
        )
        cur.execute("select account_id from workers where id=%s", (worker_id,))
        account_row=cur.fetchone()
        record_audit_event(
            cur,
            "EXPIRED",
            "assignment",
            assignment_id,
            account_id=account_row[0] if account_row else None,
            worker_id=worker_id,
            payload={"job_id":str(job_id),"timeout_seconds":ASSIGNMENT_TIMEOUT_SECONDS},
        )


def assignment_for_worker(cur, assignment_id: UUID, worker_id: UUID):
    cur.execute("select id,job_id,worker_id,status,started_at from job_assignments where id=%s and worker_id=%s for update", (assignment_id, worker_id))
    return cur.fetchone()


def assignment_for_account(cur, assignment_id: UUID, account_id: UUID):
    cur.execute("select a.id,a.job_id,a.worker_id,a.status,j.status from job_assignments a join workers w on w.id=a.worker_id join jobs j on j.id=a.job_id where a.id=%s and w.account_id=%s for update", (assignment_id,account_id))
    return cur.fetchone()


@app.post("/assignments/{assignment_id}/start")
def start_assignment(assignment_id: UUID, request: Request, token_worker_id: UUID = Depends(worker_id_from_token)):
    enforce_rate_limit(request, "write")
    payload={"assignment_id":str(assignment_id)}
    now = datetime.now(timezone.utc)
    with db() as conn:
        with conn.cursor() as cur:
            replay=worker_idempotency_replay(cur, token_worker_id, request, payload)
            if replay is not None:
                return replay
            expire_stale_assignments(cur)
            row=assignment_for_worker(cur,assignment_id,token_worker_id)
            if not row: raise HTTPException(404,"Assignment not found")
            if row[3]!="ASSIGNED": raise HTTPException(409,f"Assignment is {row[3]}")
            cur.execute("update job_assignments set status='RUNNING',started_at=%s,last_heartbeat_at=%s where id=%s and status='ASSIGNED'",(now,now,assignment_id))
            if cur.rowcount != 1:
                raise HTTPException(409, "Assignment changed before start")
            cur.execute("update jobs set status='RUNNING' where id=%s and status='QUEUED'",(row[1],))
            record_audit_event(cur,"STARTED","assignment",assignment_id,worker_id=token_worker_id,payload={"job_id":str(row[1])})
            response={"assignment_id":str(assignment_id),"status":"RUNNING","started_at":now}

            worker_idempotency_store(cur, token_worker_id, request, payload, response)
    return response


@app.post("/assignments/{assignment_id}/stop")
def stop_assignment(assignment_id: UUID, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    """Stop the account-owned public puzzle assignment and release the job back to QUEUED."""
    payload={"assignment_id":str(assignment_id)}
    with db() as conn:
        with conn.cursor() as cur:
            # Do not run expire_stale_assignments() here. A stale assignment is
            # still explicitly stoppable by its owner. The old ordering expired
            # it first, returned "Assignment is EXPIRED", and never signalled the
            # managed solver, which could keep running in the background.
            row=assignment_for_account(cur,assignment_id,account_id)
            if not row: raise HTTPException(404,"Assignment not found")
            if row[3] not in ("ASSIGNED","RUNNING","EXPIRED"):
                raise HTTPException(409,f"Assignment is {row[3]}")
            _stop_managed_solver(assignment_id)
            now=datetime.now(timezone.utc)
            cur.execute(
                "update job_assignments set status='RELEASED',last_heartbeat_at=null where id=%s and status in ('ASSIGNED','RUNNING','EXPIRED')",
                (assignment_id,),
            )
            if cur.rowcount != 1:
                raise HTTPException(409,"Assignment changed before stop")
            cur.execute(
                """update jobs set status='QUEUED',completed_at=null
                   where id=%s and status in ('QUEUED','RUNNING')
                     and not exists (select 1 from job_assignments where job_id=%s and status in ('ASSIGNED','RUNNING'))""",
                (row[1],row[1]),
            )
            record_audit_event(cur,"RELEASED","assignment",assignment_id,account_id,row[2],payload={**payload,"reason":"account_requested"})
            response={"assignment_id":str(assignment_id),"status":"RELEASED","stopped_at":now}
    return response

@app.post("/assignments/{assignment_id}/heartbeat")
def assignment_heartbeat(assignment_id: UUID, request: Request, token_worker_id: UUID = Depends(worker_id_from_token)):
    enforce_rate_limit(request, "write")
    payload={"assignment_id":str(assignment_id)}
    now=datetime.now(timezone.utc)
    with db() as conn:
        with conn.cursor() as cur:
            replay=worker_idempotency_replay(cur, token_worker_id, request, payload)
            if replay is not None:
                return replay
            expire_stale_assignments(cur)
            row=assignment_for_worker(cur,assignment_id,token_worker_id)
            if not row: raise HTTPException(404,"Assignment not found")
            if row[3]!="RUNNING": raise HTTPException(409,f"Assignment is {row[3]}")
            cur.execute("update job_assignments set last_heartbeat_at=%s where id=%s",(now,assignment_id))
            cur.execute("update workers set last_seen_at=%s where id=%s",(now,row[2]))
            record_audit_event(cur,"HEARTBEAT","assignment",assignment_id,worker_id=token_worker_id,payload={"job_id":str(row[1])})
            response={"assignment_id":str(assignment_id),"status":"RUNNING","heartbeat_at":now}

            worker_idempotency_store(cur, token_worker_id, request, payload, response)
    return response


@app.post("/assignments/{assignment_id}/complete")
def complete_assignment(assignment_id: UUID, request: Request, token_worker_id: UUID = Depends(worker_id_from_token)):
    enforce_rate_limit(request, "write")
    payload={"assignment_id":str(assignment_id)}
    now=datetime.now(timezone.utc)
    with db() as conn:
        with conn.cursor() as cur:
            replay=worker_idempotency_replay(cur, token_worker_id, request, payload)
            if replay is not None:
                return replay
            expire_stale_assignments(cur)
            row=assignment_for_worker(cur,assignment_id,token_worker_id)
            if not row: raise HTTPException(404,"Assignment not found")
            if row[3]!="RUNNING": raise HTTPException(409,f"Assignment is {row[3]}")
            cur.execute("select w.account_id from workers w where w.id=%s", (token_worker_id,))
            account_row=cur.fetchone()
            if not account_row: raise HTTPException(404,"Worker not found")
            account_id=account_row[0]
            started_at=row[4]
            if not started_at:
                raise HTTPException(409, "Assignment has no server start time")
            seconds=max(0,int((now-started_at).total_seconds()))
            cur.execute("update job_assignments set status='COMPLETED',completed_at=%s,last_heartbeat_at=%s,verified_seconds=%s where id=%s and status='RUNNING'",(now,now,seconds,assignment_id))
            if cur.rowcount != 1:
                raise HTTPException(409, "Assignment changed before completion")
            cur.execute(
                """update jobs set status=case
                       when exists (
                         select 1 from job_assignments
                         where job_id=%s and status in ('ASSIGNED','RUNNING')
                       ) then 'RUNNING'
                       else 'COMPLETED'
                     end,
                     completed_at=case
                       when exists (
                         select 1 from job_assignments
                         where job_id=%s and status in ('ASSIGNED','RUNNING')
                       ) then null
                       else %s
                     end
                   where id=%s and status='RUNNING'""",
                (row[1],row[1],now,row[1]),
            )
            period_start=started_at.date()
            end_date=now.date()
            while period_start <= end_date:
                day_start=datetime.combine(period_start, datetime.min.time(), tzinfo=timezone.utc)
                day_end=day_start+timedelta(days=1)
                segment_start=max(started_at,day_start)
                segment_end=min(now,day_end)
                segment_seconds=max(0,int((segment_end-segment_start).total_seconds()))
                if segment_seconds:
                    cur.execute(
                        "insert into worker_hours(id,account_id,worker_id,period_start,seconds_verified) values(%s,%s,%s,%s,%s) "
                        "on conflict(worker_id,period_start) do update set seconds_verified=worker_hours.seconds_verified+excluded.seconds_verified",
                        (uuid4(),account_id,row[2],period_start,segment_seconds),
                    )
                period_start += timedelta(days=1)
            record_audit_event(cur,"COMPLETED","assignment",assignment_id,account_id,row[2],{"job_id":str(row[1]),"contribution_seconds":seconds})
            response={"assignment_id":str(assignment_id),"status":"COMPLETED","contribution_seconds":seconds}

            worker_idempotency_store(cur, token_worker_id, request, payload, response)
    return response


def auto_credit_verified_claim(cur, job_id, claim_id, worker_id, candidate_hash):
    cur.execute(
        "select j.puzzle_id,j.status,c.challenge_type,c.reward_btc,c.balance_btc,c.status,c.rules,c.provenance,c.verification,c.payout "
        "from jobs j join challenge_registry c on c.id=j.puzzle_id "
        "where j.id=%s and j.scope='public-reward-challenge' for update",
        (job_id,),
    )
    job=cur.fetchone()
    if not job:
        return None
    record={
        "id":job[0],"type":job[2],"reward_btc":job[3],"balance_btc":job[4],
        "status":job[5],"rules":job[6],"provenance":job[7],"verification":job[8],"payout":job[9],
    }
    result=verify_candidate_hash(record,candidate_hash)
    if not result["verified"]:
        cur.execute(
            "update work_claims set result_status='REJECTED' where id=%s and result_status='TESTED'",
            (claim_id,),
        )
        return {"verified":False,"reason":result["reason"]}
    cur.execute(
        "update work_claims set result_status='VERIFIED' where id=%s and result_status='TESTED'",
        (claim_id,),
    )
    if cur.rowcount != 1:
        return None
    cur.execute(
        "update jobs set status='VERIFIED',completed_at=coalesce(completed_at,now()) where id=%s",
        (job_id,),
    )
    cur.execute("select account_id from workers where id=%s for update",(worker_id,))
    account_row=cur.fetchone()
    if not account_row:
        raise HTTPException(404,"Worker account not found")
    account_id=account_row[0]
    event=build_reward_event(account_id,job[0],job[3])
    if Decimal(str(event["worker_share_btc"])) + Decimal(str(event["platform_fee_btc"])) != Decimal(str(event["gross_reward_btc"])):
        raise HTTPException(500,"Reward split integrity check failed")
    treasury_available = treasury_available_btc(cur)
    gross_reward = Decimal(str(event["gross_reward_btc"]))
    if treasury_available < gross_reward:
        raise HTTPException(409, "Treasury is underfunded for this verified reward")
    reward_id=uuid4()
    cur.execute(
        "insert into reward_events(id,account_id,puzzle_id,gross_reward_btc,worker_share_btc,platform_fee_btc,settlement_status,source_claim_id,approved_at) "
        "values(%s,%s,%s,%s,%s,%s,'APPROVED',%s,now()) "
        "on conflict (puzzle_id,account_id) where settlement_status <> 'VOID' do nothing returning id",
        (reward_id,account_id,job[0],event["gross_reward_btc"],event["worker_share_btc"],event["platform_fee_btc"],claim_id),
    )
    inserted=cur.fetchone()
    if not inserted:
        return {"verified":True,"already_credited":True}
    reward_id=inserted[0]
    worker_share = Decimal(str(event["worker_share_btc"]))
    owner_share = Decimal(str(event["platform_fee_btc"]))
    cur.execute(
        "update treasury_accounting set solver_liability_btc=solver_liability_btc+%s, owner_liability_btc=owner_liability_btc+%s, updated_at=now() where id=%s",
        (worker_share, owner_share, TREASURY_WALLET_ID),
    )
    treasury_ledger(cur, "REWARD_LIABILITY", gross_reward, "REWARD_EVENT", reward_id, account_id=account_id)
    cur.execute(
        "insert into reward_balances(account_id,available_btc,updated_at) values(%s,%s,now()) "
        "on conflict(account_id) do update set available_btc=reward_balances.available_btc+excluded.available_btc,updated_at=now()",
        (account_id,event["worker_share_btc"]),
    )
    cur.execute(
        "insert into reward_ledger(id,account_id,reward_event_id,entry_type,amount_btc) values(%s,%s,%s,'WORKER_CREDIT',%s) "
        "on conflict(reward_event_id,entry_type) do nothing",
        (uuid4(),account_id,reward_id,event["worker_share_btc"]),
    )
    owner_address=(record.get("payout") or {}).get("owner_btc_address")
    if not owner_address:
        raise HTTPException(500,"Challenge owner BTC address is missing from the verified payout metadata")
    cur.execute(
        "insert into reward_ledger(id,account_id,reward_event_id,entry_type,amount_btc,destination_btc_address) values(%s,%s,%s,'PLATFORM_FEE',%s,%s)",
        (uuid4(),account_id,reward_id,event["platform_fee_btc"],owner_address),
    )
    treasury_ledger(cur, "OWNER_LIABILITY", owner_share, "REWARD_EVENT", reward_id,
                    account_id=account_id, destination_btc_address=owner_address)
    withdrawal_queued=False
    cur.execute(
        "insert into notifications(id,account_id,event_type,title,message,metadata) "
        "values(%s,%s,'REWARD_CREDITED','Reward credited','Your verified puzzle solution was accepted. "
        "Your 85% solver reward has been credited to your BTC Rewards balance.',%s::jsonb)",
        (uuid4(),account_id,json.dumps({
            "reward_id":str(reward_id),
            "job_id":str(job_id),
            "reward_btc":str(event["worker_share_btc"]),
            "owner_share_btc":str(event["platform_fee_btc"]),
            "owner_btc_address":owner_address,
        })),
    )
    record_audit_event(
        cur,"AUTO_REWARD_CREDITED","reward_event",reward_id,account_id,worker_id,
        {"job_id":str(job_id),"claim_id":str(claim_id),"worker_share_btc":event["worker_share_btc"],
         "platform_fee_btc":event["platform_fee_btc"],"withdrawal_queued":withdrawal_queued,"treasury_address":TREASURY_BTC_ADDRESS,"custody":"central_treasury"},
    )
    return {
        "verified":True,"reward_id":str(reward_id),
        "worker_credit_btc":event["worker_share_btc"],
        "platform_fee_btc":event["platform_fee_btc"],
        "withdrawal_queued":withdrawal_queued,
    }


@app.post("/jobs/{job_id}/claims")
def claim(job_id: UUID, body: ClaimCreate, request: Request, token_worker_id: UUID = Depends(worker_id_from_token)):
    enforce_rate_limit(request, "write")
    payload=body.model_dump()
    with db() as conn:
        with conn.cursor() as cur:
            replay=worker_idempotency_replay(cur, token_worker_id, request, payload)
            if replay is not None:
                return replay
            expire_stale_assignments(cur)
            cur.execute(
                "select a.id,a.worker_id,a.status,j.status,a.started_at from job_assignments a "
                "join jobs j on j.id=a.job_id join workers w on w.id=a.worker_id "
                "where a.id=%s and a.job_id=%s and w.id=%s for update",
                (body.assignment_id, job_id, token_worker_id),
            )
            assignment = cur.fetchone()
            if not assignment: raise HTTPException(404,"Assignment not found")
            if token_worker_id != body.worker_id or assignment[1] != token_worker_id:
                raise HTTPException(403,"Worker token does not match claim worker")
            if assignment[2] != "RUNNING": raise HTTPException(409,"Assignment must be RUNNING before claims are accepted")
            if assignment[3] not in ("QUEUED","RUNNING"): raise HTTPException(409,"Job is no longer accepting claims")
            if body.result_status == "VERIFIED":
                raise HTTPException(403, "VERIFIED claims require a server-side challenge adapter.")
            # CPU time is an accounting signal, not worker-authoritative proof.
            # Bound it by server-observed wall time and the worker's declared
            # thread capacity so a client cannot manufacture arbitrary compute.
            started_at=assignment[4]
            if not started_at:
                raise HTTPException(409, "Assignment has no server start time")
            elapsed_seconds=max(0,int((datetime.now(timezone.utc)-started_at).total_seconds()))
            cur.execute("select coalesce(cpu_threads,1) from worker_capabilities where worker_id=%s", (token_worker_id,))
            capability_row=cur.fetchone()
            cpu_threads=max(1,int(capability_row[0] if capability_row else 1))
            server_cpu_ceiling=min(86400, elapsed_seconds*cpu_threads)
            accepted_cpu_seconds=min(body.cpu_seconds, server_cpu_ceiling)

            cid=uuid4()
            duplicate=False
            try:
                # A savepoint keeps the surrounding idempotency/audit transaction
                # alive when the database rejects a duplicate candidate.
                with conn.transaction():
                    cur.execute(
                        "insert into work_claims(id,job_id,worker_id,candidate_hash,result_status,cpu_seconds,finished_at) "
                        "values(%s,%s,%s,%s,%s,%s,now())",
                        (cid,job_id,body.worker_id,body.candidate_hash,body.result_status,accepted_cpu_seconds),
                    )
            except psycopg.errors.UniqueViolation:
                duplicate=True

            if duplicate:
                cur.execute(
                    "insert into security_events(id,worker_id,event_type,severity,metadata) "
                    "values(%s,%s,'DUPLICATE_CLAIM','WARN',%s::jsonb)",
                    (uuid4(),token_worker_id,json.dumps({"job_id":str(job_id),"candidate_hash":body.candidate_hash})),
                )
                raise HTTPException(409, "Duplicate candidate claim")

            record_audit_event(
                cur,"CLAIM_SUBMITTED","job",job_id,worker_id=token_worker_id,
                payload={
                    "assignment_id":str(body.assignment_id),
                    "candidate_hash":body.candidate_hash,
                    "result_status":body.result_status,
                    "cpu_seconds":accepted_cpu_seconds,
                },
            )
            auto_result = auto_credit_verified_claim(cur, job_id, cid, token_worker_id, body.candidate_hash)
            response={"accepted":True,"claim_id":str(cid),"result_status":body.result_status,
                      "assignment_id":str(body.assignment_id),"cpu_seconds":accepted_cpu_seconds,
                      "auto_verification":auto_result}
            worker_idempotency_store(cur, token_worker_id, request, payload, response)
            return response


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


@app.get("/audit/job/{job_id}/verify")
def verify_job_audit(job_id: UUID):
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select event_type,entity_type,entity_id,account_id,worker_id,payload,previous_hash,event_hash from audit_events order by created_at asc,id asc")
            events=cur.fetchall()
    previous=None
    valid_events=0
    for e in events:
        canonical=json.dumps({
            "event_type":e[0],"entity_type":e[1],"entity_id":e[2],
            "account_id":str(e[3]) if e[3] else None,
            "worker_id":str(e[4]) if e[4] else None,
            "payload":e[5],"previous_hash":previous,
        }, sort_keys=True, separators=(",", ":"), default=str).encode()
        expected=hashlib.sha256(canonical).hexdigest()
        if e[6] != previous or e[7] != expected:
            return {"valid":False,"events_checked":valid_events,"reason":"audit-chain-integrity-failure"}
        if e[1] == "job" and e[2] == str(job_id):
            valid_events += 1
        previous=e[7]
    return {"valid":True,"events_checked":valid_events,"head_hash":previous}

@app.get("/scheduler/recommendations")
def scheduler_recommendations(limit: int = 10):
    limit = max(1, min(limit, 50))
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select j.id,j.puzzle_id,c.title,c.reward_btc,c.balance_btc,c.status,"
                "coalesce(o.estimated_seconds,0),coalesce(o.estimated_difficulty,0) "
                "from jobs j join challenge_registry c on c.id=j.puzzle_id "
                "left join lateral (select estimated_seconds,estimated_difficulty from challenge_offers "
                "where challenge_id=c.id and status='PUBLISHED' order by published_at desc nulls last,created_at desc limit 1) o on true "
                "where j.scope='public-reward-challenge' and j.status='QUEUED' and c.status='OPEN + FUNDED' and c.balance_btc > 0 "
                "and c.funding_match=true and c.verification_stale=false "
                "order by c.balance_btc desc limit %s", (limit * 3,))
            rows = cur.fetchall()
            recommendations = []
            for job_id,puzzle_id,title,reward,balance,status,estimated_seconds,difficulty in rows:
                seconds = int(estimated_seconds or 0)
                if seconds <= 0:
                    seconds = max(3600, int(float(difficulty or 1) * 3600))
                cur.execute(
                    "select count(*) filter (where result_status='VERIFIED'), count(*) "
                    "from work_claims where job_id=%s and finished_at > now() - interval '30 days'",
                    (job_id,)
                )
                verified_claims, recent_claims = cur.fetchone()
                success_probability = (verified_claims / recent_claims) if recent_claims else 0.01
                score = economic_priority(float(balance), seconds, success_probability, 1.0)
                reason = {
                    "estimated_success_probability": round(success_probability, 8),
                    "verified_claims_30d": verified_claims,
                    "claims_30d": recent_claims,
                    "estimated_worker_seconds": seconds,
                    "funded_balance_btc": float(balance),
                    "policy": "expected_reward_per_worker_hour"
                }
                cur.execute(
                    "select 1 from scheduler_decisions where job_id=%s and created_at > now() - interval '5 minutes' limit 1",
                    (job_id,)
                )
                if cur.fetchone() is None:
                    cur.execute(
                        "insert into scheduler_decisions(id,job_id,score,reason) values(%s,%s,%s,%s::jsonb)",
                        (uuid4(), job_id, score, json.dumps(reason))
                    )
                recommendations.append({
                    "job_id": str(job_id),
                    "puzzle_id": puzzle_id,
                    "title": title,
                    "funded_balance_btc": float(balance),
                    "estimated_worker_seconds": seconds,
                    "priority_score": score,
                    "reason": reason
                })
            recommendations.sort(key=lambda x: x["priority_score"], reverse=True)
            return {"recommendations": recommendations[:limit]}


class PSBTReady(BaseModel):
    unsigned_psbt: str = Field(min_length=20, max_length=200000)
    signer_id: str = Field(min_length=1, max_length=120)

class SignedPayout(BaseModel):
    signed_psbt: str = Field(min_length=20, max_length=400000)
    final_tx_hex: str = Field(min_length=100, max_length=400000)
    signer_id: str = Field(min_length=1, max_length=120)

class BroadcastPayout(BaseModel):
    txid: str = Field(min_length=64, max_length=64)
    broadcaster_id: str = Field(min_length=1, max_length=120)

def require_payout_signer(request: Request):
    if not PAYOUT_SIGNER_TOKEN:
        raise HTTPException(503, "Payout signer is not configured")
    supplied = request.headers.get("x-payout-signer-token", "")
    if not hmac.compare_digest(supplied, PAYOUT_SIGNER_TOKEN):
        raise HTTPException(401, "Invalid payout signer credential")

def _read_varint(buf, offset):
    if offset >= len(buf):
        raise ValueError("truncated varint")
    n = buf[offset]
    offset += 1
    if n < 0xfd:
        return n, offset
    size = {0xfd: 2, 0xfe: 4, 0xff: 8}[n]
    if offset + size > len(buf):
        raise ValueError("truncated varint")
    return int.from_bytes(buf[offset:offset + size], "little"), offset + size

def _tx_outputs(tx_hex: str):
    try:
        raw = bytes.fromhex(tx_hex)
        off = 4
        vin_count, off = _read_varint(raw, off)
        segwit = vin_count == 0
        if segwit:
            if off + 2 > len(raw) or raw[off] != 1:
                raise ValueError("invalid segwit marker")
            off += 2
            vin_count, off = _read_varint(raw, off)
        for _ in range(vin_count):
            if off + 36 > len(raw): raise ValueError("truncated input")
            off += 36
            n, off = _read_varint(raw, off); off += n + 4
            if off > len(raw): raise ValueError("truncated input")
        vout_count, off = _read_varint(raw, off)
        outputs=[]
        for _ in range(vout_count):
            if off + 8 > len(raw): raise ValueError("truncated output")
            amount=int.from_bytes(raw[off:off+8],"little"); off += 8
            n, off = _read_varint(raw, off)
            script=raw[off:off+n]; off += n
            outputs.append((amount, script))
        if segwit:
            for _ in range(vin_count):
                n, off = _read_varint(raw, off)
                for __ in range(n):
                    ln, off = _read_varint(raw, off); off += ln
        if off + 4 != len(raw): raise ValueError("unexpected transaction trailing data")
        return raw, outputs
    except (ValueError, IndexError, KeyError) as exc:
        raise HTTPException(422, f"Invalid Bitcoin transaction: {exc}")

def _scriptpubkey_for_mainnet_address(address: str) -> bytes:
    value=address.strip()
    if _base58check_valid(value):
        n=0
        for ch in value: n=n*58+BASE58_ALPHABET.index(ch)
        raw=n.to_bytes((n.bit_length()+7)//8,"big") if n else b""
        leading=len(value)-len(value.lstrip("1")); raw=b"\\x00"*leading+raw
        payload=raw[:-4]; version=payload[0]; h=payload[1:]
        if version == 0 and len(h) == 20: return b"\\x76\\xa9\\x14"+h+b"\\x88\\xac"
        if version == 5 and len(h) == 20: return b"\\xa9\\x14"+h+b"\\x87"
        raise HTTPException(422,"Unsupported payout address type")
    a=value.lower(); pos=a.rfind("1")
    data=[BECH32_CHARSET.index(ch) for ch in a[pos+1:]]
    payload=_convertbits(data[1:-6],5,8,False); version=data[0]
    h=bytes(payload)
    if version == 0 and len(h) in (20,32): return bytes([0,len(h)])+h
    if version == 1 and len(h)==32: return b"\\x51\\x20"+h
    raise HTTPException(422,"Unsupported payout address type")

def _psbt_unsigned_tx(psbt_text: str) -> bytes:
    try:
        raw=base64.b64decode(psbt_text, validate=True)
        if not raw.startswith(b"psbt\\xff"): raise ValueError("invalid PSBT magic")
        off=5
        while True:
            klen,off=_read_varint(raw,off)
            if klen == 0: break
            if off+klen > len(raw): raise ValueError("truncated global key")
            key=raw[off:off+klen]; off += klen
            vlen,off=_read_varint(raw,off)
            if off+vlen > len(raw): raise ValueError("truncated global value")
            val=raw[off:off+vlen]; off += vlen
            if key == b"\\x00": return val
        raise ValueError("PSBT does not contain a global unsigned transaction")
    except (ValueError, IndexError) as exc:
        raise HTTPException(422, f"Invalid PSBT: {exc}")

def _payout_digest(amount_btc, destination, tx_bytes):
    amount_sat=int(Decimal(str(amount_btc))*Decimal("100000000"))
    return hashlib.sha256(json.dumps(
        {"amount_sat":amount_sat,"destination":destination,"unsigned_tx":base64.b64encode(tx_bytes).decode()},
        sort_keys=True,separators=(",",":")).encode()).hexdigest()

def _verify_payout_transaction(tx_hex, amount_btc, destination):
    raw,outputs=_tx_outputs(tx_hex)
    expected_script=_scriptpubkey_for_mainnet_address(destination)
    amount_sat=int(Decimal(str(amount_btc))*Decimal("100000000"))
    if sum(n for n,script in outputs if script == expected_script) != amount_sat:
        raise HTTPException(422,"Signed transaction does not pay the exact withdrawal amount to the destination")
    txid=hashlib.sha256(hashlib.sha256(raw).digest()).digest()[::-1].hex()
    return txid,raw

def validate_psbt_text(value: str) -> str:
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception:
        raise HTTPException(422, "PSBT must be valid base64")
    if not raw.startswith(b"psbt\xff"):
        raise HTTPException(422, "Invalid PSBT magic header")
    if len(raw) > 300000:
        raise HTTPException(413, "PSBT is too large")
    return value

def validate_txid(value: str) -> str:
    v=value.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", v):
        raise HTTPException(422, "txid must be a 64-character hexadecimal Bitcoin transaction id")
    return v

class WithdrawalComplete(BaseModel):
    external_reference: str = Field(min_length=3, max_length=200)


@app.get("/admin/withdrawals")
def list_withdrawals(request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    with db() as conn:
        with conn.cursor() as cur:
            require_owner(cur, account_id)
            cur.execute("""
                select id,account_id,amount_btc,payout_address,status,external_reference,created_at,processed_at
                from withdrawal_requests
                where status in ('QUEUED','PROCESSING')
                order by created_at asc
                limit 100
            """)
            rows=cur.fetchall()
    return {"withdrawals":[
        {"id":str(r[0]),"account_id":str(r[1]),"amount_btc":float(r[2]),"payout_address":r[3],
         "status":r[4],"external_reference":r[5],"created_at":r[6],"processed_at":r[7]}
        for r in rows
    ]}


@app.post("/admin/withdrawals/{withdrawal_id}/processing")
def start_withdrawal_processing(withdrawal_id: UUID, request: Request, account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    payload={"withdrawal_id":str(withdrawal_id)}
    with db() as conn:
        with conn.cursor() as cur:
            replay=idempotency_replay(cur, account_id, request, payload)
            if replay is not None:
                return replay
            require_owner(cur, account_id)
            cur.execute(
                "update withdrawal_requests set status='PROCESSING' where id=%s and status='QUEUED' returning account_id,amount_btc,payout_address",
                (withdrawal_id,),
            )
            row=cur.fetchone()
            if not row:
                raise HTTPException(409,"Withdrawal is not queued")
            record_audit_event(cur,"WITHDRAWAL_PROCESSING","withdrawal",withdrawal_id,account_id,
                payload={"beneficiary_account":str(row[0]),"amount_btc":str(row[1]),"payout_address_present":True,"custody":"none"})
            response={"withdrawal_id":str(withdrawal_id),"status":"PROCESSING","custody":"non-custodial"}
            idempotency_store(cur, account_id, request, payload, response)
            return response


@app.post("/admin/withdrawals/{withdrawal_id}/complete")
def complete_withdrawal_legacy_blocked(withdrawal_id: UUID, request: Request,
                                       account_id: UUID = Depends(account_id_from_auth)):
    enforce_rate_limit(request, "write")
    raise HTTPException(410, "Manual TXID settlement is disabled. Use the secure PSBT settlement rail.")

@app.post("/internal/payouts/{withdrawal_id}/psbt")
def submit_unsigned_psbt(withdrawal_id: UUID, body: PSBTReady, request: Request):
    require_payout_signer(request)
    psbt=validate_psbt_text(body.unsigned_psbt)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select ps.id,ps.status,ps.amount_btc,ps.destination_btc_address "
                "from payout_settlements ps join withdrawal_requests w on w.id=ps.withdrawal_id "
                "where ps.withdrawal_id=%s for update",
                (withdrawal_id,),
            )
            row=cur.fetchone()
            if not row: raise HTTPException(404,"Payout settlement not found")
            if row[1] not in ("PSBT_REQUESTED","PSBT_READY"): raise HTTPException(409,"Settlement is not awaiting an unsigned PSBT")
            cur.execute(
                "update payout_settlements set unsigned_psbt=%s,signer_id=%s,status='PSBT_READY',updated_at=now() where id=%s",
                (psbt,body.signer_id,row[0]),
            )
            cur.execute(
                "insert into payout_settlement_events(id,settlement_id,event_type,signer_id,metadata) values(%s,%s,'PSBT_READY',%s,%s::jsonb)",
                (uuid4(),row[0],body.signer_id,json.dumps({"amount_btc":str(row[2]),"destination_btc_address":row[3]})),
            )
    return {"withdrawal_id":str(withdrawal_id),"settlement_id":str(row[0]),"status":"PSBT_READY"}

@app.post("/internal/payouts/{withdrawal_id}/signed")
def submit_signed_psbt(withdrawal_id: UUID, body: SignedPayout, request: Request):
    require_payout_signer(request)
    signed=validate_psbt_text(body.signed_psbt)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id,status,unsigned_psbt,amount_btc,destination_btc_address from payout_settlements "
                "where withdrawal_id=%s for update",(withdrawal_id,),
            )
            row=cur.fetchone()
            if not row: raise HTTPException(404,"Payout settlement not found")
            if row[1] != "PSBT_READY": raise HTTPException(409,"Settlement is not ready for signing")
            if not row[2]: raise HTTPException(409,"Unsigned PSBT is missing")
            signed_unsigned_tx=_psbt_unsigned_tx(signed)
            original_unsigned_tx=_psbt_unsigned_tx(row[2])
            if signed_unsigned_tx != original_unsigned_tx:
                raise HTTPException(422,"Signed PSBT does not match the approved unsigned transaction")
            digest=_payout_digest(row[3],row[4],signed_unsigned_tx)
            cur.execute("select payout_digest from payout_settlements where id=%s",(row[0],))
            stored_digest=cur.fetchone()[0]
            if not stored_digest or not hmac.compare_digest(stored_digest,digest):
                raise HTTPException(409,"Payout intent digest mismatch")
            computed_txid,_=_verify_payout_transaction(body.final_tx_hex,row[3],row[4])
            cur.execute(
                "update payout_settlements set signed_psbt=%s,signed_tx_hex=%s,signer_id=%s,status='SIGNED',signed_at=now(),updated_at=now() where id=%s",
                (signed,body.final_tx_hex,body.signer_id,row[0]),
            )
            cur.execute(
                "insert into payout_settlement_events(id,settlement_id,event_type,signer_id,metadata) values(%s,%s,'SIGNED',%s,%s::jsonb)",
                (uuid4(),row[0],body.signer_id,json.dumps({"amount_btc":str(row[3]),"destination_btc_address":row[4]})),
            )
    return {"withdrawal_id":str(withdrawal_id),"settlement_id":str(row[0]),"status":"SIGNED"}

@app.post("/internal/payouts/{withdrawal_id}/broadcast")
def confirm_broadcast(withdrawal_id: UUID, body: BroadcastPayout, request: Request):
    require_payout_signer(request)
    txid=validate_txid(body.txid)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id,status,amount_btc,destination_btc_address,signed_tx_hex from payout_settlements "
                "where withdrawal_id=%s for update",(withdrawal_id,),
            )
            row=cur.fetchone()
            if not row: raise HTTPException(404,"Payout settlement not found")
            if row[1] not in ("SIGNED","BROADCAST"): raise HTTPException(409,"Settlement is not signed")
            if not row[4]: raise HTTPException(409,"Signed PSBT is missing")
            computed_txid,_=_verify_payout_transaction(row[4],row[2],row[3])
            if not hmac.compare_digest(computed_txid,txid):
                raise HTTPException(422,"Broadcast TXID does not match the signed transaction")
            cur.execute(
                "update payout_settlements set status='BROADCAST',txid=%s,updated_at=now(),broadcast_at=coalesce(broadcast_at,now()) where id=%s",
                (txid,row[0]),
            )
            cur.execute(
                "insert into payout_settlement_events(id,settlement_id,event_type,signer_id,txid,metadata) values(%s,%s,'BROADCAST',%s,%s,%s::jsonb)",
                (uuid4(),row[0],body.broadcaster_id,txid,json.dumps({"amount_btc":str(row[2]),"destination_btc_address":row[3]})),
            )
    return {"withdrawal_id":str(withdrawal_id),"settlement_id":str(row[0]),"status":"BROADCAST","txid":txid}

@app.post("/internal/payouts/{withdrawal_id}/settle")
def settle_broadcast(withdrawal_id: UUID, request: Request):
    require_payout_signer(request)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select ps.id,ps.status,ps.txid,w.account_id,w.amount_btc "
                "from payout_settlements ps join withdrawal_requests w on w.id=ps.withdrawal_id "
                "where ps.withdrawal_id=%s for update",(withdrawal_id,),
            )
            row=cur.fetchone()
            if not row: raise HTTPException(404,"Payout settlement not found")
            if row[1] != "BROADCAST" or not row[2]: raise HTTPException(409,"Payout has not been broadcast")
            cur.execute(
                "update withdrawal_requests set status='PAID',external_reference=%s,processed_at=now() "
                "where id=%s and status='PROCESSING' returning id",
                (row[2],withdrawal_id),
            )
            if cur.rowcount != 1: raise HTTPException(409,"Withdrawal is not PROCESSING")
            cur.execute(
                "update payout_settlements set status='SETTLED',settled_at=now(),updated_at=now() where id=%s",
                (row[0],),
            )
            cur.execute(
                "update treasury_accounting set reserved_btc=reserved_btc-%s,updated_at=now() where id=%s and reserved_btc >= %s",
                (row[4],TREASURY_WALLET_ID,row[4]),
            )
            if cur.rowcount != 1: raise HTTPException(409,"Treasury reservation is inconsistent")
            treasury_ledger(cur,"USER_WITHDRAWAL_SETTLED",row[4],"WITHDRAWAL",withdrawal_id,account_id=row[3])
            cur.execute(
                "insert into payout_settlement_events(id,settlement_id,event_type,txid,metadata) values(%s,%s,'SETTLED',%s,%s::jsonb)",
                (uuid4(),row[0],row[2],json.dumps({"amount_btc":str(row[4])})),
            )
            record_audit_event(cur,"WITHDRAWAL_PAID","withdrawal",withdrawal_id,row[3],
                payload={"amount_btc":str(row[4]),"external_reference":row[2],"rail":"PSBT","custody":"central_treasury"})
    return {"withdrawal_id":str(withdrawal_id),"status":"PAID","external_reference":row[2],"rail":"PSBT","custody":"central_treasury"}

@app.post("/internal/payouts/next")
def payout_worker_next(request: Request):
    require_payout_worker(request)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("select pg_advisory_xact_lock(58392017)")
            cur.execute(
                "select w.id,w.account_id,w.amount_btc,w.payout_address,w.status,ps.id,ps.status,ps.unsigned_psbt,ps.signed_psbt,ps.signed_tx_hex "
                "from withdrawal_requests w left join payout_settlements ps on ps.withdrawal_id=w.id "
                "where (w.status='QUEUED' and ps.id is null) "
                "or (w.status='PROCESSING' and w.processed_at is null and w.created_at < now() - (%s || ' minutes')::interval "
                "and (ps.id is null or ps.status in ('PSBT_REQUESTED','PSBT_READY','SIGNED'))) "
                "order by w.created_at asc limit 1 for update skip locked",
                (PAYOUT_RETRY_AFTER_MINUTES,),
            )
            row=cur.fetchone()
            if not row:
                return {"withdrawal":None}
            wid,account_id,amount,address,status,existing_settlement_id,existing_settlement_status,existing_unsigned_psbt,existing_signed_psbt,existing_signed_tx_hex=row
            amount=Decimal(str(amount))
            if amount > MAX_SINGLE_PAYOUT_BTC:
                record_audit_event(cur,"WITHDRAWAL_BLOCKED","withdrawal",wid,account_id,
                    payload={"reason":"MAX_SINGLE_PAYOUT_BTC","amount_btc":str(amount),"limit_btc":str(MAX_SINGLE_PAYOUT_BTC)})
                cur.execute("update withdrawal_requests set status='FAILED',processed_at=now() where id=%s and status in ('QUEUED','PROCESSING')",(wid,))
                return {"withdrawal":None,"blocked":"MAX_SINGLE_PAYOUT_BTC","withdrawal_id":str(wid)}
            cur.execute(
                "select coalesce(sum(amount_btc),0) from withdrawal_requests "
                "where status='PAID' and processed_at >= current_date",
            )
            paid_today=Decimal(str(cur.fetchone()[0] or 0))
            if paid_today + amount > MAX_DAILY_PAYOUT_BTC:
                record_audit_event(cur,"WITHDRAWAL_BLOCKED","withdrawal",wid,account_id,
                    payload={"reason":"MAX_DAILY_PAYOUT_BTC","amount_btc":str(amount),
                             "paid_today_btc":str(paid_today),"limit_btc":str(MAX_DAILY_PAYOUT_BTC)})
                return {"withdrawal":None,"blocked":"MAX_DAILY_PAYOUT_BTC","withdrawal_id":str(wid)}
            cur.execute(
                "update withdrawal_requests set status='PROCESSING' where id=%s and status in ('QUEUED','PROCESSING') returning id",
                (wid,),
            )
            if cur.rowcount != 1:
                return {"withdrawal":None}
            settlement_id=existing_settlement_id
            settlement_status=existing_settlement_status
            if settlement_id is None:
                settlement_id=uuid4()
                cur.execute(
                    "insert into payout_settlements(id,withdrawal_id,wallet_id,amount_btc,destination_btc_address,status) "
                    "values(%s,%s,%s,%s,%s,'PSBT_REQUESTED')",
                    (settlement_id,wid,TREASURY_WALLET_ID,amount,address),
                )
                settlement_status="PSBT_REQUESTED"
                cur.execute("update withdrawal_requests set settlement_id=%s where id=%s",(settlement_id,wid))
                cur.execute(
                    "insert into payout_settlement_events(id,settlement_id,event_type,metadata) values(%s,%s,'PSBT_REQUESTED',%s::jsonb)",
                    (uuid4(),settlement_id,json.dumps({"amount_btc":str(amount),"destination_btc_address":address})),
                )
            else:
                # Resume the existing safe-to-retry settlement instead of creating
                # a second payout intent for the same withdrawal.
                cur.execute(
                    "insert into payout_settlement_events(id,settlement_id,event_type,metadata) values(%s,%s,'SETTLEMENT_RESUMED',%s::jsonb)",
                    (uuid4(),settlement_id,json.dumps({"status":settlement_status})),
                )
            record_audit_event(cur,"WITHDRAWAL_PROCESSING","withdrawal",wid,account_id,
                payload={"amount_btc":str(amount),"payout_address_present":True,
                         "settlement_id":str(settlement_id),"rail":"PSBT",
                         "max_single_btc":str(MAX_SINGLE_PAYOUT_BTC),"max_daily_btc":str(MAX_DAILY_PAYOUT_BTC),
                         "custody":"central_treasury"})
            return {"withdrawal":{"id":str(wid),"account_id":str(account_id),"amount_btc":float(amount),
                                  "payout_address":address,"status":"PROCESSING","settlement_id":str(settlement_id),
                                  "settlement_status":settlement_status,"unsigned_psbt":existing_unsigned_psbt,
                                  "signed_psbt":existing_signed_psbt,"final_tx_hex":existing_signed_tx_hex,
                                  "idempotency_key":str(wid)}}


@app.post("/internal/payouts/{withdrawal_id}/complete")
def payout_worker_complete_legacy_blocked(withdrawal_id: UUID, request: Request):
    require_payout_worker(request)
    raise HTTPException(410, "Legacy payout completion is disabled. Use the secure PSBT settlement rail.")

