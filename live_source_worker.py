"""Periodic live-source synchronizer with exact escrow-spend evidence."""
import json, os
from datetime import datetime, timezone
import psycopg
from challenge_sources import OpenCryptoPuzzlesAdapter
from strategy_router import choose_strategy
from adaptive_rotation import rank_challenges
from challenge_telemetry import collect_from_rows

DATABASE_URL = os.environ.get("DATABASE_URL","")
SOURCE_ID = "open-crypto-puzzles-v2"
TELEMETRY_WINDOW_SECONDS = 3600
HEARTBEAT_TIMEOUT_SECONDS = 120

def now():
    return datetime.now(timezone.utc).isoformat()

def _upsert(cur, record, solve_evidence=None):
    r = record.as_registry()
    v = r["verification"]
    decision = choose_strategy(r)
    metrics = dict(r.get("search_metrics") or {})
    metrics["strategy_action"] = decision.action
    metrics["strategy_reason"] = decision.reason
    metrics["strategy_score"] = decision.score
    metrics["strategy_confidence"] = decision.confidence
    metrics["strategy_signals"] = decision.signals
    r["search_metrics"] = metrics
    snapshot = {"addresses": v.get("addresses", []), "checked_at": v.get("checked_at"), "dual_explorer_match": v.get("dual_explorer_match", False)}
    cur.execute(
        """insert into challenge_registry
          (id,title,challenge_type,reward_btc,balance_btc,status,rules,provenance,
           verification,payout,source_adapter,live_checked_at,live_verification,
           advertised_reward_btc,verified_balance_btc,funding_match,
           verification_stale,last_live_check_error,funding_snapshot,solve_evidence,
           search_metrics,expected_value_score)
        values
          (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb,
           %s,%s,%s,false,null,%s::jsonb,%s::jsonb,%s::jsonb,%s)
        on conflict(id) do update set
          title=excluded.title, challenge_type=excluded.challenge_type,
          reward_btc=excluded.reward_btc, balance_btc=excluded.balance_btc,
          status=case when challenge_registry.status='EXTERNAL_SOLVED'
                      then challenge_registry.status else excluded.status end,
          rules=excluded.rules, provenance=excluded.provenance,
          verification=excluded.verification, payout=excluded.payout,
          source_adapter=excluded.source_adapter, live_checked_at=excluded.live_checked_at,
          live_verification=excluded.live_verification, advertised_reward_btc=excluded.advertised_reward_btc,
          verified_balance_btc=excluded.verified_balance_btc, funding_match=excluded.funding_match,
          verification_stale=false, last_live_check_error=null, funding_snapshot=excluded.funding_snapshot,
          search_metrics=excluded.search_metrics, expected_value_score=excluded.expected_value_score,
          solve_evidence=case when challenge_registry.solve_evidence <> '{}'::jsonb
            then challenge_registry.solve_evidence else excluded.solve_evidence end,
          updated_at=now()""",
        (r["id"], r["title"], r["challenge_type"], r["reward_btc"], r["balance_btc"], r["status"], r["rules"],
         json.dumps(r["provenance"]), json.dumps(r["verification"]), json.dumps(r["payout"]), r["source_adapter"],
         v["checked_at"], json.dumps({"addresses": r["addresses"], "live": True}), v["advertised_reward_btc"],
         v["verified_balance_btc"], v["funding_match"], json.dumps(snapshot), json.dumps(solve_evidence or {}),
         json.dumps(r.get("search_metrics") or {}),
         float((r.get("search_metrics") or {}).get("expected_value_score", 0) or 0)))

def _refresh_telemetry(cur, records):
    """Overlay server-observed worker telemetry before adaptive ranking."""
    refreshed = []
    for item in records:
        r = item.as_registry()
        metrics = dict(r.get("search_metrics") or {})
        total = metrics.get("keyspace_total")
        searched = metrics.get("keyspace_searched", 0)
        try:
            total = int(total) if total is not None else None
            searched = int(searched or 0)
        except (TypeError, ValueError):
            total, searched = None, 0
        cur.execute(
            """select ja.worker_id,ja.status assignment_status,ja.last_heartbeat_at,
                      w.last_seen_at worker_last_seen_at,ja.started_at,ja.assigned_at,
                      ja.verified_seconds,count(wc.id) claim_count
                 from job_assignments ja
                 join jobs j on j.id=ja.job_id
                 join workers w on w.id=ja.worker_id
                 left join work_claims wc on wc.job_id=ja.job_id
                    and wc.started_at >= now() - (%s * interval '1 second')
                where j.puzzle_id=%s and j.scope='public-reward-challenge'
                  and ja.status in ('ASSIGNED','RUNNING')
                group by ja.worker_id,ja.status,ja.last_heartbeat_at,w.last_seen_at,
                         ja.started_at,ja.assigned_at,ja.verified_seconds""",
            (TELEMETRY_WINDOW_SECONDS, item.id),
        )
        rows = [dict(zip(
            ("worker_id","assignment_status","last_heartbeat_at","worker_last_seen_at",
             "started_at","assigned_at","verified_seconds","claim_count"), row
        )) for row in cur.fetchall()]
        telemetry = collect_from_rows(
            rows, reward_btc=float(r.get("reward_btc") or 0),
            claim_window_seconds=TELEMETRY_WINDOW_SECONDS,
            heartbeat_timeout_seconds=HEARTBEAT_TIMEOUT_SECONDS,
            keyspace_total=total, keyspace_searched=searched,
            measured_attempts_per_second=metrics.get("audited_attempts_per_second"),
            reliability=float(metrics.get("reliability") or 1.0),
        )
        # Preserve catalog/source fields while making provenance explicit.
        merged = dict(metrics)
        merged.update(telemetry)
        decision_record = dict(r)
        decision_record["search_metrics"] = merged
        decision = choose_strategy(decision_record)
        merged["strategy_action"] = decision.action
        merged["strategy_reason"] = decision.reason
        merged["strategy_score"] = decision.score
        merged["strategy_confidence"] = decision.confidence
        merged["strategy_signals"] = decision.signals
        cur.execute(
            """update challenge_registry
               set search_metrics=%s::jsonb, expected_value_score=%s, updated_at=now()
               where id=%s""",
            (json.dumps(merged), float(merged.get("expected_value_score") or 0), item.id),
        )
        cur.execute(
            """insert into challenge_metric_snapshots(id,challenge_id,metrics,captured_at)
               values(gen_random_uuid(),%s,%s::jsonb,now())""",
            (item.id, json.dumps(merged)),
        )
        refreshed.append({**r, "search_metrics": merged})
    return refreshed

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
                cur.execute("""select status,balance_btc,payout,funding_snapshot
                               from challenge_registry where id=%s for update""", (item.id,))
                previous = cur.fetchone()
                previous_balance = float(previous[1]) if previous else 0.0
                previous_snapshot = (previous[3] or {}) if previous else {}
                evidence = []
                if previous_snapshot.get("addresses"):
                    evidence = source.btc.exact_outspend_evidence([
                        u for address in previous_snapshot.get("addresses", [])
                        for u in address.get("live_utxos", [])
                    ])
                authoritative = bool(item.verification.get("escrow_spend_is_authoritative"))
                _upsert(cur, item, {"status":"CANDIDATE","verified":False,"exact_spends":evidence} if evidence else None)
                if authoritative and evidence and previous_balance > 0 and item.balance_btc <= 0:
                    chosen = evidence[0]
                    solve = {"status":"SOLVED","verified":True,"evidence_url":chosen["evidence_url"],
                             "evidence_id":chosen["spending_txid"],"funding_txid":chosen["funding_txid"],
                             "funding_vout":chosen["funding_vout"],"funding_value_sats":chosen["funding_value_sats"],
                             "source":"exact-escrow-utxo-spend","checked_at":now()}
                    cur.execute("""update challenge_registry
                                   set status='EXTERNAL_SOLVED',external_status=%s::jsonb,
                                       solve_evidence=%s::jsonb,retired_at=now(),
                                       retired_reason='authoritative_exact_escrow_spend',updated_at=now()
                                   where id=%s""",(json.dumps(solve),json.dumps(solve),item.id))
                    cur.execute("""insert into challenge_rotation_events
                                   (id,challenge_id,event_type,evidence_url,evidence_id,previous_status,next_status)
                                   values(gen_random_uuid(),%s,'EXTERNAL_SOLVED',%s,%s,'OPEN + FUNDED','EXTERNAL_SOLVED')""",
                                (item.id,solve["evidence_url"],solve["evidence_id"]))
                    cur.execute("""update jobs set status='EXPIRED',completed_at=now()
                                   where puzzle_id=%s and scope='public-reward-challenge'
                                   and status in ('QUEUED','RUNNING')""",(item.id,))
                    solved.append(item.id)

            cur.execute("""select id from challenge_registry
                           where source_adapter=%s and status in ('OPEN + FUNDED','OPEN + UNFUNDED')""",(SOURCE_ID,))
            for (cid,) in cur.fetchall():
                if cid not in discovered_ids:
                    cur.execute("""update challenge_registry
                                   set verification_stale=true,last_live_check_error=%s,updated_at=now()
                                   where id=%s""",
                                ("Source did not return this puzzle during sync; last known on-chain state preserved.",cid))

            registry_records = _refresh_telemetry(cur, records)
            rotation = rank_challenges(registry_records)
            for ranked in rotation["ranked"]:
                metrics = dict(ranked.get("search_metrics") or {})
                metrics["opportunity_score"] = ranked.get("opportunity_score", 0)
                cur.execute(
                    "update challenge_registry set search_metrics=%s::jsonb, expected_value_score=%s, updated_at=now() where id=%s",
                    (json.dumps(metrics), float(ranked.get("strategy", {}).get("score") or 0), ranked["id"]),
                )
            for ranked in rotation["queue"]:
                cid = ranked["id"]
                cur.execute("""insert into jobs(id,puzzle_id,scope,status)
                               select gen_random_uuid(),%s,'public-reward-challenge','QUEUED'
                               where exists (
                                 select 1 from challenge_registry
                                 where id=%s and status='OPEN + FUNDED' and balance_btc>0
                                   and funding_match=true and verification_stale=false
                                   and payout->>'permissionless'='true'
                                   and payout->>'automatic_chain_claim'='true'
                                   and verification->>'execution_mode'='COMPUTE'
                                   and verification->>'adapter_runnable'='true')
                                 and not exists (
                                   select 1 from jobs where puzzle_id=%s
                                   and scope='public-reward-challenge' and status in ('QUEUED','RUNNING'))""",(cid,cid,cid))

            cur.execute("""update jobs set status='EXPIRED',completed_at=now()
                           where scope='public-reward-challenge' and status='QUEUED'
                             and puzzle_id in (
                               select id from challenge_registry
                               where coalesce(verification->>'execution_mode','RESEARCH') <> 'COMPUTE'
                                  or coalesce(verification->>'adapter_runnable','false') <> 'true')""")

            for retired in solved:
                cur.execute("""select id from challenge_registry
                               where status='OPEN + FUNDED' and balance_btc>0 and funding_match=true
                                 and verification_stale=false and payout->>'permissionless'='true'
                                 and payout->>'automatic_chain_claim'='true'
                               order by expected_value_score desc,balance_btc desc,updated_at desc,id asc limit 1""")
                replacement = cur.fetchone()
                if not replacement:
                    cur.execute("""insert into challenge_rotation_events
                                   (id,challenge_id,event_type,previous_status,next_status)
                                   values(gen_random_uuid(),%s,'NO_ELIGIBLE_REPLACEMENT',
                                          'EXTERNAL_SOLVED','EXTERNAL_SOLVED')""",(retired,))
                    continue
                rid = replacement[0]
                cur.execute("""insert into jobs(id,puzzle_id,scope,status)
                               select gen_random_uuid(),%s,'public-reward-challenge','QUEUED'
                               where not exists (
                                 select 1 from jobs where puzzle_id=%s
                                 and scope='public-reward-challenge' and status in ('QUEUED','RUNNING'))""",(rid,rid))
                cur.execute("""insert into challenge_rotation_events
                               (id,challenge_id,event_type,previous_status,next_status)
                               values(gen_random_uuid(),%s,'ROTATED_IN',null,'OPEN + FUNDED')""",(rid,))

    return {"discovered":len(records),"funding_changed_to_unfunded":changed_to_unfunded,"externally_solved":len(solved)}

if __name__ == "__main__":
    print(json.dumps(sync(), default=str))
