import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest


DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="PostgreSQL integration database not configured")


def db():
    return psycopg.connect(DATABASE_URL)


def apply_schema(conn):
    schema = (Path(__file__).resolve().parents[1] / "backend" / "schema.sql").read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(schema)
    conn.commit()


def test_schema_and_core_constraints():
    with db() as conn:
        apply_schema(conn)
        account = uuid4()
        worker = uuid4()
        job = uuid4()
        assignment_a = uuid4()
        assignment_b = uuid4()
        claim_a = uuid4()
        claim_b = uuid4()
        with conn.cursor() as cur:
            cur.execute("insert into accounts(id,email) values(%s,%s)", (account, f"test-{account}@example.invalid"))
            cur.execute("insert into workers(id,account_id,label) values(%s,%s,%s)", (worker, account, "integration"))
            cur.execute(
                "insert into jobs(id,puzzle_id,scope,status) values(%s,%s,'public-reward-challenge','QUEUED')",
                (job, "integration"),
            )
            cur.execute(
                "insert into job_assignments(id,job_id,worker_id,status) values(%s,%s,%s,'ASSIGNED')",
                (assignment_a, job, worker),
            )
            cur.execute("savepoint duplicate_assignment")
            with pytest.raises(psycopg.errors.UniqueViolation):
                cur.execute(
                    "insert into job_assignments(id,job_id,worker_id,status) values(%s,%s,%s,'RUNNING')",
                    (assignment_b, job, worker),
                )
            cur.execute("rollback to savepoint duplicate_assignment")
            cur.execute(
                "insert into work_claims(id,job_id,worker_id,candidate_hash,result_status) values(%s,%s,%s,%s,'TESTED')",
                (claim_a, job, worker, "a" * 64),
            )
            cur.execute("savepoint duplicate_claim")
            with pytest.raises(psycopg.errors.UniqueViolation):
                cur.execute(
                    "insert into work_claims(id,job_id,worker_id,candidate_hash,result_status) values(%s,%s,%s,%s,'TESTED')",
                    (claim_b, job, worker, "a" * 64),
                )
            cur.execute("rollback to savepoint duplicate_claim")
        conn.rollback()


def test_concurrent_active_assignment_insert_allows_only_one():
    account = uuid4()
    worker = uuid4()
    job = uuid4()

    with db() as conn:
        apply_schema(conn)
        with conn.cursor() as cur:
            cur.execute("insert into accounts(id,email) values(%s,%s)", (account, f"race-{account}@example.invalid"))
            cur.execute("insert into workers(id,account_id) values(%s,%s)", (worker, account))
            cur.execute(
                "insert into jobs(id,puzzle_id,scope,status) values(%s,%s,'public-reward-challenge','QUEUED')",
                (job, "race"),
            )
        conn.commit()

    def attempt():
        aid = uuid4()
        try:
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "insert into job_assignments(id,job_id,worker_id,status) values(%s,%s,%s,'ASSIGNED')",
                        (aid, job, worker),
                    )
                conn.commit()
            return True
        except psycopg.errors.UniqueViolation:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))

    assert sum(results) == 1
