import json, os
from datetime import datetime, timezone
import psycopg
from challenge_sources import OpenCryptoPuzzlesAdapter, _fetch_json
DATABASE_URL=os.environ.get('DATABASE_URL','')
SOURCE_ID='open-crypto-puzzles-v1'
def now(): return datetime.now(timezone.utc).isoformat()
def sync():
    if not DATABASE_URL: raise RuntimeError('DATABASE_URL is required')
    source=OpenCryptoPuzzlesAdapter(); records=source.discover(); solved=[]
    with psycopg.connect(DATABASE_URL) as conn:
      with conn.cursor() as cur:
        for item in records:
          r=item.as_registry()
          cur.execute("""insert into challenge_registry (id,title,challenge_type,reward_btc,balance_btc,status,rules,provenance,verification,payout,source_adapter,live_checked_at,live_verification) values (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb) on conflict(id) do update set title=excluded.title,challenge_type=excluded.challenge_type,reward_btc=excluded.reward_btc,balance_btc=excluded.balance_btc,status=case when challenge_registry.status='EXTERNAL_SOLVED' then challenge_registry.status else excluded.status end,provenance=excluded.provenance,verification=excluded.verification,payout=excluded.payout,source_adapter=excluded.source_adapter,live_checked_at=excluded.live_checked_at,live_verification=excluded.live_verification,updated_at=now()""",(r['id'],r['title'],r['challenge_type'],r['reward_btc'],r['balance_btc'],r['status'],r['rules'],json.dumps(r['provenance']),json.dumps(r['verification']),json.dumps(r['payout']),r['source_adapter'],r['verification']['checked_at'],json.dumps({'addresses':r['addresses'],'live':True})))
        cur.execute("select id,balance_btc,live_verification from challenge_registry where source_adapter=%s and status='OPEN + FUNDED' for update",(SOURCE_ID,))
        for cid,old_balance,meta in cur.fetchall():
          total=0; spent=None; failed=False
          for item in (meta or {}).get('addresses',[]):
            if item.get('chain')!='bitcoin': continue
            try:
              state=source.btc.state(item['address']); stats=state.get('chain_stats',{})
              total += max(0,int(stats.get('funded_txo_sum',0))-int(stats.get('spent_txo_sum',0)))
              if int(stats.get('spent_txo_count',0))>0 and spent is None: spent=item['address']
            except Exception: failed=True; break
          if failed: continue
          live=total/100000000
          cur.execute('update challenge_registry set balance_btc=%s,live_checked_at=now(),updated_at=now() where id=%s',(live,cid))
          if float(old_balance)>0 and live<=0 and spent:
            txs=_fetch_json(f"{source.btc.base_url}/address/{spent}/txs"); txid=txs[0].get('txid') if txs else None
            if txid:
              evidence={'status':'SOLVED','verified':True,'evidence_url':f"{source.btc.base_url}/tx/{txid}",'evidence_id':txid,'source':'live-public-escrow','checked_at':now()}
              cur.execute("update challenge_registry set status='EXTERNAL_SOLVED',external_status=%s::jsonb,retired_at=now(),retired_reason='authoritative_external_solution',updated_at=now() where id=%s",(json.dumps(evidence),cid))
              cur.execute("insert into challenge_rotation_events(id,challenge_id,event_type,evidence_url,evidence_id,previous_status,next_status) values(gen_random_uuid(),%s,'EXTERNAL_SOLVED',%s,%s,'OPEN + FUNDED','EXTERNAL_SOLVED')",(cid,evidence['evidence_url'],txid)); cur.execute("update jobs set status='EXPIRED',completed_at=now() where puzzle_id=%s and scope='public-reward-challenge' and status in ('QUEUED','RUNNING')",(cid,)); solved.append(cid)
        for retired in solved:
          cur.execute("select id from challenge_registry where status='OPEN + FUNDED' and balance_btc>0 and payout->>'permissionless'='true' and payout->>'automatic_chain_claim'='true' order by balance_btc desc,updated_at desc,id asc limit 1")
          row=cur.fetchone()
          if not row:
            cur.execute("insert into challenge_rotation_events(id,challenge_id,event_type,previous_status,next_status) values(gen_random_uuid(),%s,'NO_ELIGIBLE_REPLACEMENT','EXTERNAL_SOLVED','EXTERNAL_SOLVED')",(retired,)); continue
          rid=row[0]
          cur.execute("insert into jobs(id,puzzle_id,scope,status) select gen_random_uuid(),%s,'public-reward-challenge','QUEUED' where not exists (select 1 from jobs where puzzle_id=%s and scope='public-reward-challenge' and status in ('QUEUED','RUNNING'))",(rid,rid))
          cur.execute("insert into challenge_rotation_events(id,challenge_id,event_type,previous_status,next_status) values(gen_random_uuid(),%s,'ROTATED_IN',null,'OPEN + FUNDED')",(rid,))
    return {'discovered':len(records),'externally_solved':len(solved)}
if __name__=='__main__': print(json.dumps(sync(),default=str))
