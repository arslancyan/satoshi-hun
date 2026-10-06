import os
from pathlib import Path
import psycopg

ROOT=Path(__file__).resolve().parents[1]
DB=os.environ.get("DATABASE_URL")
if not DB: raise SystemExit("DATABASE_URL is required")
files=[ROOT/"backend"/"schema.sql"]+sorted((ROOT/"backend"/"migrations").glob("*.sql"))
if os.environ.get("SATOSHI_HUNT_ENV","production").lower() == "staging":
    files.append(ROOT/"backend"/"staging_fixture.sql")
with psycopg.connect(DB) as conn:
    with conn.cursor() as cur:
        for path in files:
            cur.execute(path.read_text(encoding="utf-8"))
            print("APPLIED",path)
print("DATABASE INITIALIZED")
