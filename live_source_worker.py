"""Periodic live-source synchronizer.

Balance changes are data changes, not proof of a solve. A challenge is retired
only when exact funded escrow output(s) have authoritative payout evidence.
Explorer failures preserve the last known state.
"""
import json
import os
from datetime import datetime, timezone
import psycopg
from challenge_sources import OpenCryptoPuzzlesAdapter

DATABASE_URL=os.environ.get("DATABASE_URL","")
SOURCE_ID="open-crypto-puzzles-v2"

def now(): return datetime.now(timezone.utc).isoformat()

def _upsert(cur, record):
    r=record.as_registry(); v=r["verification"]
    cur.execute("""
      insert into challenge_registry
        (id,title,challenge_type,reward_btc,balance_btc,status,rules,provenance,
         verification,payout,source_adapter,live_checked_at,live_verification,
         advertised_reward_btc,verified_balance_btc,funding_match,
         verification_stale,last_live_check_error)
      values (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb,
              %s,%s,%s,false,null)
      on conflict(id) do update set
        title=excluded.title, challenge_type=excluded.challenge_type,
        reward_btc=excluded.reward_btc, balance_btc=excluded.balance_btc,
        status=case when challenge_registry.status='EXTERNAL_SOLVED'
                    then challenge_registry.status else excluded.status end,
        rules=excluded.rules, provenance=excluded.provenance,
        verification=excluded.verification, payout=excluded.payout,
        source_adapter=excluded.source_adapter,
        live_checked_at=excluded.live_checked_at,
        live_verification=excluded.live_verification,
        advertised_reward_btc=excluded.advertised_reward_btc,
        verified_balance_btc=excluded.verified_balance_btc,
        funding_match=excluded.funding_match,
        verification_stale=false, last_live_check_error=null, updated_at=now()
    """,(r["id"],r["title"],r["challenge_type"],r["reward_btc"],r["balance_btc"],
         r["status"],r["rules"],json.dumps(r["provenance"]),json.dumps(r["verification"]),
         json.dumps(r["payout"]),r["source_adapter"],v["checked_at"],
         json.dumps({"addresses":r["addresses"],"live":True}),
         v["advertised_reward_btc"],v["verified_balance_btc"],v["funding_match"]))

def sync():
    if not DATABASE_URL: raise RuntimeError("DATABASE_URL is required")
    source=OpenCryptoPuzzlesAdapter()
    records=source.discover()
    discovered_ids={x.id for x in records}
    changed_to_unfunded=0
    with psycopg.connect(DATABASE_URL) as conn:
      with conn.cursor() as cur:
        for item in records:
          row=None
          cur.execute("select status,balance_btc from challenge_registry where id=%s",(item.id,))
          row=cur.fetchone()
          _upsert(cur,item)
          if row and row[0]=="OPEN + FUNDED" and item.status!="OPEN + FUNDED":
            changed_to_unfunded += 1
        cur.execute("""select id from challenge_registry
                       where source_adapter=%s and status in ('OPEN + FUNDED','OPEN + UNFUNDED')""",(SOURCE_ID,))
        for (cid,) in cur.fetchall():
          if cid not in discovered_ids:
            cur.execute("""update challenge_registry
                           set verification_stale=true,
                               last_live_check_error=%s, updated_at=now()
                           where id=%s""",
                        ("Source did not return this puzzle during sync; last known on-chain state preserved.",cid))
    return {"discovered":len(records),"funding_changed_to_unfunded":changed_to_unfunded,"externally_solved":0}

if __name__=="__main__": print(json.dumps(sync(),default=str))
