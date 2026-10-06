from pathlib import Path

p=Path("/app/backend/api.py")
s=p.read_text()

old='''            cur.execute("select id from job_assignments where job_id=%s and status in ('ASSIGNED','RUNNING')",(job_id,))
            if cur.fetchone(): raise HTTPException(409,"Challenge is already being run by another worker")
            capacity=economic_capacity(cur,job_id)'''
new='''            cur.execute("select id,status from job_assignments where job_id=%s and worker_id=%s and status in ('ASSIGNED','RUNNING')",(job_id,body.worker_id))
            existing_assignment=cur.fetchone()
            if existing_assignment:
                response={"challenge_id":challenge_id,"job_id":str(job_id),"assignment_id":str(existing_assignment[0]),"worker_id":str(body.worker_id),"status":existing_assignment[1]}
                idempotency_store(cur,account_id,request,payload,response)
                return response
            capacity=economic_capacity(cur,job_id)'''
if old not in s:
    raise SystemExit("run challenge patch target not found")
s=s.replace(old,new,1)

old2='''    cur.execute(
        "update jobs set status='VERIFIED',completed_at=coalesce(completed_at,now()) where id=%s",
        (job_id,),
    )'''
new2='''    cur.execute(
        "update jobs set status='VERIFIED',completed_at=coalesce(completed_at,now()) where id=%s",
        (job_id,),
    )
    cur.execute(
        "update job_assignments set status='COMPLETED',completed_at=now(),last_heartbeat_at=null "
        "where id=(select id from job_assignments where job_id=%s and worker_id=%s and status='RUNNING' order by assigned_at desc limit 1)",
        (job_id,worker_id),
    )
    cur.execute(
        "update job_assignments set status='RELEASED',completed_at=now(),last_heartbeat_at=null "
        "where job_id=%s and status in ('ASSIGNED','RUNNING')",
        (job_id,),
    )'''
if old2 not in s:
    raise SystemExit("reward patch target not found")
s=s.replace(old2,new2,1)
p.write_text(s)
