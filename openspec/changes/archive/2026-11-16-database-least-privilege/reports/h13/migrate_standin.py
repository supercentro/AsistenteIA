"""STAND-IN for the planned `db-migrate` (it does not exist yet): Alembic as the migrator, then the grants of the matrix in ONE transaction
(table-level revoke, then grant). Runs as a one-shot Compose service in the real backend image. Prints no secret."""
import os
import subprocess
import sys

import psycopg

p = subprocess.run(["python", "-m", "alembic", "upgrade", "head"], cwd="/app", capture_output=True, text=True)
tail = (p.stdout + p.stderr).strip().splitlines()
print("alembic rc", p.returncode, (tail[-1] if tail else "")[:110], flush=True)
if p.returncode != 0:
    sys.exit(1)

APP = "asistente_app"
WORKER = "asistente_worker"
GRANTS = [
    f"GRANT SELECT, INSERT ON users TO {APP}",
    f"GRANT UPDATE (consent_version, consent_accepted_at) ON users TO {APP}",
    f"GRANT SELECT, INSERT, DELETE ON subjects TO {APP}",
    f"GRANT UPDATE (description) ON subjects TO {APP}",
    f"GRANT SELECT, INSERT, DELETE ON enrollments TO {APP}",
    f"GRANT SELECT, INSERT, DELETE ON documents TO {APP}",
    f"GRANT SELECT, INSERT ON ingestion_jobs TO {APP}",
    f"GRANT SELECT ON document_chunks TO {APP}",
    f"GRANT SELECT (id, subject_id, filename, content_type, status) ON documents TO {WORKER}",
    f"GRANT UPDATE (status, chunks_count, error_code, error_message) ON documents TO {WORKER}",
    f"GRANT SELECT (id, document_id, payload, attempts, locked_by, locked_until, available_at, created_at) ON ingestion_jobs TO {WORKER}",
    f"GRANT UPDATE (payload, attempts, locked_by, locked_until, updated_at) ON ingestion_jobs TO {WORKER}",
    f"GRANT INSERT ON document_chunks TO {WORKER}",
    f"GRANT SELECT (id) ON document_chunks TO {WORKER}",
]
TABLES = ["users", "subjects", "enrollments", "documents", "document_chunks", "ingestion_jobs"]
url = os.environ["DATABASE_URL"].replace("+psycopg", "")
with psycopg.connect(url) as c:
    with c.transaction():
        for t in TABLES:
            c.execute(f"REVOKE ALL ON {t} FROM {APP}, {WORKER}")
        for g in GRANTS:
            c.execute(g)
print("grants applied in one transaction:", len(GRANTS), flush=True)
