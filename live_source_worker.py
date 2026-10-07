"""Periodic live-source synchronizer with exact escrow-spend evidence."""
import json, os
from datetime import datetime, timezone
import psycopg
from challenge_sources import OpenCryptoPuzzlesAdapter

DATABASE_URL = os.environ.get("DATABASE_URL","")
SOURCE_ID = "open-crypto-puzzles-v2"
# Highest-priority BTC research challenges selected from the live catalog.
# These are public, funded puzzles with strong published leads, but they are
# not treated as generic hash-search jobs unless a challenge-specific solver
# adapter exists.
PRIORITY_BTC_CHALLENGES = (
    "keir-finlow-bates-blockchain-book-600ksats",
    "corey-phillips-kitten-passphrase-1msats",
    "rushwallet-contest-30-1msats",
)

def now():
    return datetime.now(timezone.utc).isoformat()

def _upsert(cur, record, solve_evidence=None):
    r = record.as_registry()
    v = r["verification"]
    snapshot = {
        "addresses": v.get("addresses", []),
        "checked_at": v.get("checked_at"),
        "dual_explorer_match": v.get("dual_explorer_match", False),
    }
    cur.execute(
        """insert into challenge_registry
          (id,title,challenge_type,reward_btc,balance_btc,status,rules,provenance,
           verification,payout,source_adapter,live_checked_at,live_verification,
           advertised_reward_btc,verified_balance_btc,funding_match,
           verification_stale,last_live_check_error,funding_snapshot,solve_evidence)
        values
          (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb,
           %s,%s,%s,false,null,%s::jsonb,%s::jsonb)
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
          verification_stale=false, last_live_check_error=null,
          funding_snapshot=excluded.funding_snapshot,
          solve_evidence=case
            when challenge_registry.solve_evidence <> '{}'::jsonb
            then challenge_registry.solve_evidence
            else excluded.solve_evidence
          end,
          updated_at=now()
        """,
        (
            r["id"], r["title"], r["challenge_type"], r["reward_btc"],
            r["balance_btc"], r["status"], r["rules"],
            json.dumps(r["provenance"]), json.dumps(r["verification"]),
            json.dumps(r["payout"]), r["source_adapter"], v["checked_at"],
            json.dumps({"addresses": r["addresses"], "live": True}),
            v["advertised_reward_btc"], v["verified_balance_btc"],
            v["funding_match"], json.dumps(snapshot),
            json.dumps(solve_evidence or {}),
        ),
    )

def sync():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required")
    source = OpenCryptoPuzzlesAdapter()
    records = source.discover()
    discovered_ids = {x.id for x in records}
    solved = []
    changed_to_unfunded = 0

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for item in records:
                cur.execute(
                    """select status,balance_btc,payout,funding_snapshot
                       from challenge_registry where id=%s for update""",
                    (item.id,),
                )
                previous = cur.fetchone()
                previous_balance = float(previous[1]) if previous else 0.0
                previous_snapshot = (previous[3] or {}) if previous else {}
                evidence = []
                if previous_snapshot.get("addresses"):
                    evidence = source.btc.exact_outspend_evidence(
                        [
                            u
                            for address in previous_snapshot.get("addresses", [])
                            for u in address.get("live_utxos", [])
                        ]
                    )

                authoritative = bool(
                    item.verification.get("escrow_spend_is_authoritative")
                )
                _upsert(
                    cur,
                    item,
                    {
                        "status": "CANDIDATE",
                        "verified": False,
                        "exact_spends": evidence,
                    }
                    if evidence
                    else None,
                )

                # A source-specific rule is mandatory. A spend alone is not a
                # universal solve signal because some puzzle creators may move
                # funds independently of a claim.
                if authoritative and evidence and previous_balance > 0 and item.balance_btc <= 0:
                    chosen = evidence[0]
                    solve = {
                        "status": "SOLVED",
                        "verified": True,
                        "evidence_url": chosen["evidence_url"],
                        "evidence_id": chosen["spending_txid"],
                        "funding_txid": chosen["funding_txid"],
                        "funding_vout": chosen["funding_vout"],
                        "funding_value_sats": chosen["funding_value_sats"],
                        "source": "exact-escrow-utxo-spend",
                        "checked_at": now(),
                    }
                    cur.execute(
                        """update challenge_registry
                           set status='EXTERNAL_SOLVED',
                               external_status=%s::jsonb,
                               solve_evidence=%s::jsonb,
                               retired_at=now(),
                               retired_reason='authoritative_exact_escrow_spend',
                               updated_at=now()
                           where id=%s""",
                        (json.dumps(solve), json.dumps(solve), item.id),
                    )
                    cur.execute(
                        """insert into challenge_rotation_events
                           (id,challenge_id,event_type,evidence_url,evidence_id,
                            previous_status,next_status)
                           values(gen_random_uuid(),%s,'EXTERNAL_SOLVED',%s,%s,
                                  'OPEN + FUNDED','EXTERNAL_SOLVED')""",
                        (item.id, solve["evidence_url"], solve["evidence_id"]),
                    )
                    cur.execute(
                        """update jobs set status='EXPIRED',completed_at=now()
                           where puzzle_id=%s and scope='public-reward-challenge'
                           and status in ('QUEUED','RUNNING')""",
                        (item.id,),
                    )
                    solved.append(item.id)

            cur.execute(
                """select id from challenge_registry
                   where source_adapter=%s
                     and status in ('OPEN + FUNDED','OPEN + UNFUNDED')""",
                (SOURCE_ID,),
            )
            for (cid,) in cur.fetchall():
                if cid not in discovered_ids:
                    cur.execute(
                        """update challenge_registry
                           set verification_stale=true,
                               last_live_check_error=%s, updated_at=now()
                           where id=%s""",
                        (
                            "Source did not return this puzzle during sync; "
                            "last known on-chain state preserved.",
                            cid,
                        ),
                    )

            # Keep a small, deliberate set of the strongest public BTC opportunities live.
            # This makes the marketplace useful even before the first external solve/rotation event.
            for cid in PRIORITY_BTC_CHALLENGES:
                cur.execute(
                    """insert into jobs(id,puzzle_id,scope,status)
                       select gen_random_uuid(),%s,'public-reward-challenge','QUEUED'
                       where exists (
                         select 1 from challenge_registry
                         where id=%s and status='OPEN + FUNDED'
                           and balance_btc>0 and funding_match=true
                           and verification_stale=false
                           and payout->>'permissionless'='true'
                           and payout->>'automatic_chain_claim'='true'
                       )
                         and not exists (
                           select 1 from jobs
                           where puzzle_id=%s and scope='public-reward-challenge'
                             and status in ('QUEUED','RUNNING')
                         )""",
                    (cid,cid,cid),
                )

            for retired in solved:
                cur.execute(
                    """select id from challenge_registry
                       where status='OPEN + FUNDED'
                         and balance_btc>0
                         and funding_match=true
                         and verification_stale=false
                         and payout->>'permissionless'='true'
                         and payout->>'automatic_chain_claim'='true'
                       order by balance_btc desc,updated_at desc,id asc
                       limit 1"""
                )
                replacement = cur.fetchone()
                if not replacement:
                    cur.execute(
                        """insert into challenge_rotation_events
                           (id,challenge_id,event_type,previous_status,next_status)
                           values(gen_random_uuid(),%s,'NO_ELIGIBLE_REPLACEMENT',
                                  'EXTERNAL_SOLVED','EXTERNAL_SOLVED')""",
                        (retired,),
                    )
                    continue
                rid = replacement[0]
                cur.execute(
                    """insert into jobs(id,puzzle_id,scope,status)
                       select gen_random_uuid(),%s,'public-reward-challenge','QUEUED'
                       where not exists (
                         select 1 from jobs
                         where puzzle_id=%s and scope='public-reward-challenge'
                           and status in ('QUEUED','RUNNING')
                       )""",
                    (rid, rid),
                )
                cur.execute(
                    """insert into challenge_rotation_events
                       (id,challenge_id,event_type,previous_status,next_status)
                       values(gen_random_uuid(),%s,'ROTATED_IN',null,'OPEN + FUNDED')""",
                    (rid,),
                )

    return {
        "discovered": len(records),
        "funding_changed_to_unfunded": changed_to_unfunded,
        "externally_solved": len(solved),
    }

if __name__ == "__main__":
    print(json.dumps(sync(), default=str))
