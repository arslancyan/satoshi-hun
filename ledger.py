"""Persistent local work ledger for distributed public-challenge workers."""
import hashlib, json, os, sqlite3, time
from contextlib import closing

DB_PATH=os.environ.get("SATOSHI_HUNT_DB","satoshi_hunt.db")

def _db():
    db=sqlite3.connect(DB_PATH)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS work (
      work_hash TEXT PRIMARY KEY,
      puzzle_id TEXT NOT NULL,
      account_id TEXT NOT NULL,
      device_id TEXT NOT NULL,
      status TEXT NOT NULL,
      first_seen REAL NOT NULL,
      last_seen REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS accounts (
      account_id TEXT PRIMARY KEY,
      created_at REAL NOT NULL,
      success_fee_bps INTEGER NOT NULL DEFAULT 1500
    );
    CREATE TABLE IF NOT EXISTS rewards (
      reward_id TEXT PRIMARY KEY,
      puzzle_id TEXT NOT NULL,
      account_id TEXT NOT NULL,
      gross_btc REAL NOT NULL,
      fee_btc REAL NOT NULL,
      user_btc REAL NOT NULL,
      status TEXT NOT NULL,
      created_at REAL NOT NULL
    );
    """)
    return db

def fingerprint(puzzle_id, candidate):
    raw=f"{puzzle_id}|{candidate}".encode()
    return hashlib.sha256(raw).hexdigest()

def claim_work(puzzle_id, candidate, account_id, device_id):
    h=fingerprint(puzzle_id,candidate); now=time.time()
    with closing(_db()) as db:
        row=db.execute("SELECT status FROM work WHERE work_hash=?",(h,)).fetchone()
        if row:
            db.execute("UPDATE work SET last_seen=? WHERE work_hash=?",(now,h))
            db.commit()
            return False, "duplicate"
        db.execute("INSERT INTO work VALUES (?,?,?,?,?,?,?)",
                   (h,str(puzzle_id),str(account_id),str(device_id),"TESTED",now,now))
        db.commit()
    return True, h

def record_reward(reward_id,puzzle_id,account_id,gross_btc,fee_bps=1500):
    gross=max(0.0,float(gross_btc)); fee=round(gross*fee_bps/10000,8)
    user=round(gross-fee,8); now=time.time()
    with closing(_db()) as db:
        db.execute("INSERT OR REPLACE INTO rewards VALUES (?,?,?,?,?,?,?,?)",
                   (reward_id,str(puzzle_id),str(account_id),gross,fee,user,"PENDING_SETTLEMENT",now))
        db.commit()
    return {"reward_id":reward_id,"gross_btc":gross,"fee_btc":fee,"user_btc":user,"fee_bps":fee_bps}

def ensure_account(account_id):
    with closing(_db()) as db:
        db.execute("INSERT OR IGNORE INTO accounts(account_id,created_at) VALUES(?,?)",(account_id,time.time()))
        db.commit()

def stats():
    with closing(_db()) as db:
        return {
          "tested": db.execute("SELECT COUNT(*) FROM work").fetchone()[0],
          "accounts": db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0],
          "rewards": db.execute("SELECT COUNT(*) FROM rewards").fetchone()[0]
        }
