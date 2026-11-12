"""Migration emulation (migrator): Alembic then the grants of the matrix, one command (the future `db-migrate`)."""
import os
import subprocess
import sys

import psycopg

p = subprocess.run(["python", "-m", "alembic", "upgrade", "head"], cwd="/app", capture_output=True, text=True)
print("alembic rc", p.returncode, (p.stdout + p.stderr).strip().splitlines()[-1][:120], flush=True)
if p.returncode != 0:
    sys.exit(1)
GRANTS = [
    "GRANT SELECT, INSERT ON users TO cs_app",
    "GRANT UPDATE (consent_version, consent_accepted_at) ON users TO cs_app",
    "GRANT SELECT, INSERT, DELETE ON subjects TO cs_app",
    "GRANT UPDATE (description) ON subjects TO cs_app",
    "GRANT SELECT, INSERT, DELETE ON enrollments TO cs_app",
    "GRANT SELECT, INSERT, DELETE ON documents TO cs_app",
    "GRANT SELECT, INSERT ON ingestion_jobs TO cs_app",
    "GRANT SELECT ON document_chunks TO cs_app",
    "GRANT SELECT (id, subject_id, filename, content_type, status) ON documents TO cs_worker",
    "GRANT UPDATE (status, chunks_count, error_code, error_message) ON documents TO cs_worker",
    "GRANT SELECT (id, document_id, payload, attempts, locked_by, locked_until, available_at, created_at) ON ingestion_jobs TO cs_worker",
    "GRANT UPDATE (payload, attempts, locked_by, locked_until, updated_at) ON ingestion_jobs TO cs_worker",
    "GRANT INSERT ON document_chunks TO cs_worker",
    "GRANT SELECT (id) ON document_chunks TO cs_worker",
]
url = os.environ["DATABASE_URL"].replace("+psycopg", "")
TABLES = ["users", "subjects", "enrollments", "documents", "document_chunks", "ingestion_jobs"]
with psycopg.connect(url) as c:  # one transaction: readers never see the revoked state
    with c.transaction():
        for t in TABLES:
            c.execute(f"REVOKE ALL ON {t} FROM cs_app, cs_worker")
        for g in GRANTS:
            c.execute(g)
print("grants applied atomically (table-level revoke then grant, one transaction):", len(GRANTS), flush=True)
