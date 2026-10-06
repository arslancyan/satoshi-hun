import hashlib
import hmac
import json
import os
import sqlite3
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

APP_VERSION = "0.1.0"
TOKEN = os.environ.get("PAYOUT_EXECUTOR_TOKEN", "").strip()
ENABLED = os.environ.get("PAYOUT_ENABLED", "false").strip().lower() == "true"
NETWORK = os.environ.get("BITCOIN_NETWORK", "mainnet").strip().lower()
MAX_SINGLE = Decimal(os.environ.get("MAX_SINGLE_PAYOUT_BTC", "0.001"))
MAX_DAILY = Decimal(os.environ.get("MAX_DAILY_PAYOUT_BTC", "0.005"))
DB_PATH = os.environ.get("EXECUTOR_DB_PATH", "/data/payout_executor.sqlite3")
RPC_URL = os.environ.get("BITCOIN_RPC_URL", "").strip()
RPC_USER = os.environ.get("BITCOIN_RPC_USER", "").strip()
RPC_PASSWORD = os.environ.get("BITCOIN_RPC_PASSWORD", "")
RPC_WALLET = os.environ.get("BITCOIN_RPC_WALLET", "").strip()
RPC_TIMEOUT = float(os.environ.get("BITCOIN_RPC_TIMEOUT_SECONDS", "30"))

app = FastAPI(title="Satoshi Hunt Payout Executor", version=APP_VERSION)

BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BECH32M = 0x2bc830a3

def db():
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("""create table if not exists payouts (
        withdrawal_id text primary key,
        idempotency_key text not null unique,
        amount_btc text not null,
        payout_address text not null,
        txid text,
        status text not null,
        created_at integer not null,
        updated_at integer not null
    )""")
    conn.commit()
    return conn

def b58check_valid(address: str) -> bool:
    if not address or any(c not in BASE58 for c in address):
        return False
    n = 0
    for c in address:
        n = n * 58 + BASE58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    leading = len(address) - len(address.lstrip("1"))
    raw = b"\x00" * leading + raw
    return len(raw) == 25 and raw[0] in (0, 5) and hashlib.sha256(hashlib.sha256(raw[:-4]).digest()).digest()[:4] == raw[-4:]

def polymod(values):
    gen = [0x3b6a57b2,0x26508e6d,0x1ea119fa,0x3d4233dd,0x2a1462b3]
    chk = 1
    for v in values:
        top = chk >> 25
        chk = ((chk & 0x1ffffff) << 5) ^ v
        for i in range(5):
            if (top >> i) & 1:
                chk ^= gen[i]
    return chk

def hrp_expand(hrp):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]

def convertbits(data, frombits, tobits):
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or value >> frombits:
            return None
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret

def bech32_valid(address: str) -> bool:
    if not address or (address.lower() != address and address.upper() != address):
        return False
    address = address.lower()
    if not address.startswith("bc1") or len(address) > 90:
        return False
    pos = address.rfind("1")
    if pos < 1 or pos + 7 > len(address):
        return False
    try:
        data = [BECH32.index(c) for c in address[pos + 1:]]
    except ValueError:
        return False
    pm = polymod(hrp_expand(address[:pos]) + data)
    if pm not in (1, BECH32M):
        return False
    if not data:
        return False
    version = data[0]
    decoded = convertbits(data[1:-6], 5, 8)
    if version > 16 or decoded is None or not 2 <= len(decoded) <= 40:
        return False
    if version == 0:
        return pm == 1 and len(decoded) in (20, 32)
    return pm == BECH32M

def valid_mainnet_address(address: str) -> bool:
    return b58check_valid(address.strip()) or bech32_valid(address.strip())

def auth(token: str | None):
    if not TOKEN:
        raise HTTPException(503, "Executor token is not configured")
    if not token or not hmac.compare_digest(token, TOKEN):
        raise HTTPException(401, "Unauthorized")

def rpc(method: str, params: list):
    if NETWORK != "mainnet":
        raise HTTPException(503, "Bitcoin mainnet is required for production payout executor")
    if not RPC_URL or not RPC_USER or not RPC_PASSWORD:
        raise HTTPException(503, "Bitcoin Core RPC signer is not configured")
    url = RPC_URL.rstrip("/")
    if RPC_WALLET:
        url += "/wallet/" + RPC_WALLET
    payload = {"jsonrpc":"1.0","id":"satoshi-hunt","method":method,"params":params}
    try:
        with httpx.Client(timeout=RPC_TIMEOUT) as client:
            r = client.post(url, json=payload, auth=(RPC_USER, RPC_PASSWORD))
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Bitcoin signer unavailable: {type(exc).__name__}") from exc
    if data.get("error"):
        raise HTTPException(502, "Bitcoin signer rejected payout")
    return data.get("result")

class PayoutRequest(BaseModel):
    withdrawal_id: str = Field(min_length=1, max_length=128)
    amount_btc: Decimal = Field(gt=0)
    payout_address: str = Field(min_length=14, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=256)

@app.get("/health")
def health():
    return {
        "ok": True,
        "enabled": ENABLED,
        "network": NETWORK,
        "signer_configured": bool(RPC_URL and RPC_USER and RPC_PASSWORD),
        "limits": {"max_single_btc": str(MAX_SINGLE), "max_daily_btc": str(MAX_DAILY)},
    }

@app.post("/payout")
def payout(body: PayoutRequest, authorization: str | None = Header(default=None)):
    auth(authorization.replace("Bearer ", "", 1) if authorization else None)
    if not ENABLED:
        raise HTTPException(503, "Payout executor is disabled")
    if NETWORK != "mainnet":
        raise HTTPException(503, "Production payout executor requires Bitcoin mainnet")
    if not valid_mainnet_address(body.payout_address):
        raise HTTPException(422, "Invalid Bitcoin mainnet payout address")
    amount = Decimal(str(body.amount_btc))
    if amount > MAX_SINGLE:
        raise HTTPException(409, "Payout exceeds executor single-payout limit")
    if amount <= 0:
        raise HTTPException(422, "Payout amount must be positive")

    conn = db()
    try:
        existing = conn.execute(
            "select txid,status,amount_btc,payout_address from payouts where withdrawal_id=? or idempotency_key=?",
            (body.withdrawal_id, body.idempotency_key),
        ).fetchone()
        if existing:
            if existing[2] != str(amount) or existing[3] != body.payout_address:
                raise HTTPException(409, "Idempotency key conflicts with an existing payout")
            if existing[0]:
                return {"txid": existing[0], "status": existing[1], "idempotent_replay": True}
            raise HTTPException(409, "Payout is already processing")

        today = time.strftime("%Y-%m-%d", time.gmtime())
        row = conn.execute(
            "select coalesce(sum(cast(amount_btc as real)),0) from payouts where status='PAID' and substr(datetime(created_at,'unixepoch'),1,10)=?",
            (today,),
        ).fetchone()
        daily = Decimal(str(row[0] or 0))
        if daily + amount > MAX_DAILY:
            raise HTTPException(409, "Daily executor payout limit reached")

        now = int(time.time())
        conn.execute(
            "insert into payouts(withdrawal_id,idempotency_key,amount_btc,payout_address,status,created_at,updated_at) values(?,?,?,?,?,?,?)",
            (body.withdrawal_id, body.idempotency_key, str(amount), body.payout_address, "PROCESSING", now, now),
        )
        conn.commit()

        try:
            txid = str(rpc("sendtoaddress", [body.payout_address, float(amount)]) or "").strip()
            if len(txid) != 64 or any(c not in "0123456789abcdefABCDEF" for c in txid):
                raise RuntimeError("Signer returned an invalid txid")
        except Exception:
            conn.execute("update payouts set status='FAILED',updated_at=? where withdrawal_id=?", (int(time.time()), body.withdrawal_id))
            conn.commit()
            raise

        conn.execute("update payouts set status='PAID',txid=?,updated_at=? where withdrawal_id=?", (txid,int(time.time()),body.withdrawal_id))
        conn.commit()
        return {"txid": txid, "status": "PAID", "idempotent_replay": False}
    finally:
        conn.close()
