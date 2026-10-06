"""Background rotation worker for real public challenges.

For the Peter Todd challenge, solved state is detected from public Bitcoin
address history. No wallet credentials are used. The worker only changes
challenge metadata and queues the next eligible challenge; it never pays out.
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

import psycopg

DATABASE_URL = os.environ.get("DATABASE_URL", "")
BLOCKSTREAM_BASE = os.environ.get("BITCOIN_EXPLORER_BASE", "https://blockstream.info/api").rstrip("/")

PETER_TODD_ADDRESSES = (
    "35Snmmy3uhaer2gTboc81ayCip4m9DT4ko",
    "3KyiQEGqqdb4nqfhUzGKN6KPhXmQsLNpay",
    "39VXyuoc6SXYKp9TcAhoiN1mb4ns6z3Yu6",
    "3DUQQvz4t57Jy7jxE86kyFcNpKtURNf1VW",
)


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Satoshi-Hunt-Rotation/1.0"})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def peter_todd_external_solution():
    """Return evidence if any published escrow has been spent."""
    for address in PETER_TODD_ADDRESSES:
        data = fetch_json(f"{BLOCKSTREAM_BASE}/address/{address}")
        stats = data.get("chain_stats", {})
        spent = int(stats.get("spent_txo_count", 0))
        if spent > 0:
            txs = fetch_json(f"{BLOCKSTREAM_BASE}/address/{address}/txs")
            txid = txs[0].get("txid") if txs else None
            return {
                "status": "SOLVED",
                "verified": bool(txid),
                "evidence_url": f"{BLOCKSTREAM_BASE}/tx/{txid}" if txid else None,
                "evidence_id": txid,
                "source": "public-bitcoin-chain",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
    return {"status":"OPEN","verified":True,"evidence_url":None,"evidence_id":None,
            "source":"public-bitcoin-chain",
            "checked_at":datetime.now(timezone.utc).isoformat()}


def run_once():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required")
    evidence = peter_todd_external_solution()
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("select id,status,balance_btc from challenge_registry where id=%s for update",
                        ("peter-todd-hash-collision-bounties",))
            row = cur.fetchone()
            if not row:
                return {"status":"missing-challenge"}
            if evidence["status"] == "SOLVED" and evidence["verified"] and row[1] != "EXTERNAL_SOLVED":
                cur.execute(
                    """update challenge_registry
                       set status='EXTERNAL_SOLVED', external_status=%s::jsonb,
                           retired_at=now(), retired_reason='authoritative_external_solution',
                           updated_at=now()
                       where id=%s""",
                    (json.dumps(evidence), row[0]),
                )
                cur.execute(
                    """insert into challenge_rotation_events
                       (id,challenge_id,event_type,evidence_url,evidence_id,previous_status,next_status)
                       values(gen_random_uuid(),%s,'EXTERNAL_SOLVED',%s,%s,%s,'EXTERNAL_SOLVED')""",
                    (row[0], evidence["evidence_url"], evidence["evidence_id"], row[1]),
                )
                # Stop new work on the externally solved challenge.
                cur.execute(
                    "update jobs set status='EXPIRED', completed_at=now() "
                    "where puzzle_id=%s and scope='public-reward-challenge' "
                    "and status in ('QUEUED','RUNNING')",
                    (row[0],),
                )
                # Select the highest-funded independently verified replacement.
                cur.execute(
                    """select id from challenge_registry
                       where status='OPEN + FUNDED' and balance_btc > 0 and id <> %s
                       and provenance->>'url' is not null
                       and verification->>'method' is not null
                       order by balance_btc desc, updated_at desc, id asc
                       limit 1""",
                    (row[0],),
                )
                replacement = cur.fetchone()
                if not replacement:
                    cur.execute(
                        """insert into challenge_rotation_events
                           (id,challenge_id,event_type,previous_status,next_status)
                           values(gen_random_uuid(),%s,'NO_ELIGIBLE_REPLACEMENT',
                                  'EXTERNAL_SOLVED','EXTERNAL_SOLVED')""",
                        (row[0],),
                    )
                    return {"rotated": False, "retired_id": row[0],
                            "replacement": None, "evidence": evidence}
                replacement_id = replacement[0]
                cur.execute(
                    """insert into jobs(id,puzzle_id,scope,status)
                       select gen_random_uuid(),%s,'public-reward-challenge','QUEUED'
                       where not exists (
                         select 1 from jobs where puzzle_id=%s
                         and scope='public-reward-challenge'
                         and status in ('QUEUED','RUNNING')
                       )""",
                    (replacement_id, replacement_id),
                )
                cur.execute(
                    """insert into challenge_rotation_events
                       (id,challenge_id,event_type,previous_status,next_status)
                       values(gen_random_uuid(),%s,'ROTATED_IN',null,'OPEN + FUNDED')""",
                    (replacement_id,),
                )
                return {"rotated": True, "retired_id": row[0],
                        "replacement": replacement_id, "evidence": evidence}
            return {"rotated": False, "status": row[1], "evidence": evidence}


if __name__ == "__main__":
    print(json.dumps(run_once(), default=str))
