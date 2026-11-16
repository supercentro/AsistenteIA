"""Stand-in for the worker/API: connects with the role it was given, prints who it is and what it sees, then waits."""
import os
import time

import psycopg

url = os.environ["DB_URL"]
with psycopg.connect(url, connect_timeout=5) as c:
    who = c.execute("select current_user").fetchone()[0]
    ver = c.execute("select version_num from alembic_version").fetchone()[0] if who != "cs_worker" else "n/a (worker has no access to alembic_version)"
    jobs = c.execute("select count(*) from ingestion_jobs").fetchone()[0]
print(f"probe connected as {who}; alembic={ver}; ingestion_jobs={jobs}; MARK={os.environ.get('MARK')}", flush=True)
time.sleep(3600)
