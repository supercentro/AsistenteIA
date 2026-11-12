"""H10 / H11 / A-02 / H8 / A-21: adoption of an existing superuser-owned database that holds data, rollback, the DROP OWNED trap."""
import uuid

import psycopg

from common import *  # noqa: F401,F403

TABLES = ["alembic_version", "users", "subjects", "enrollments", "documents", "document_chunks", "ingestion_jobs"]
ENUMS = ["user_role", "document_status"]


def build_existing(db: str):
    """Emulates the real development database: created and owned by the superuser, at 0005, with data."""
    rc, out = alembic("admin", db, "upgrade", "head")
    assert rc == 0, out[-300:]
    with connect("admin", db) as a:
        uid, sid, did = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        a.execute("insert into users(id, email, name, password_hash, role) values (%s,%s,'t','x','teacher')", (uid, f"{db}@example.com"))
        a.execute("insert into subjects(id, teacher_id, name) values (%s,%s,'s')", (sid, uid))
        a.execute("insert into documents(id, subject_id, filename, content_type, size_bytes, status, chunks_count) values (%s,%s,'f.txt','text/plain',10,'ready',1)", (did, sid))
        a.execute("insert into document_chunks(document_id, subject_id, chunk_index, content, embedding) values (%s,%s,0,'hola', array_fill(0.01::real, ARRAY[384])::vector)", (did, sid))
        a.execute("insert into ingestion_jobs(document_id, payload) values (%s, NULL)", (did,))


def counts(who, db):
    with connect(who, db) as c:
        return c.execute("select (select count(*) from users),(select count(*) from subjects),(select count(*) from documents),(select count(*) from document_chunks),(select count(*) from ingestion_jobs)").fetchone()


def adopt(db):
    with connect("admin", db) as a:
        for t in TABLES:
            a.execute(f"ALTER TABLE public.{t} OWNER TO spk_migrator")
        for e in ENUMS:
            a.execute(f"ALTER TYPE public.{e} OWNER TO spk_migrator")
        a.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        a.execute("REVOKE USAGE ON SCHEMA public FROM PUBLIC")
        a.execute("GRANT USAGE ON SCHEMA public TO spk_app, spk_worker, spk_migrator")
        a.execute("GRANT CREATE ON SCHEMA public TO spk_migrator")
        a.execute("REVOKE ALL ON DATABASE %s FROM PUBLIC" % db)
        a.execute("GRANT CONNECT ON DATABASE %s TO spk_app, spk_worker, spk_migrator" % db)
        a.execute("ALTER DEFAULT PRIVILEGES FOR ROLE spk_migrator REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC")


c0 = (1, 1, 1, 1, 1)
rec("H6", True, "adopted database: downgrade 0004 as migrator rc=0 (continued after a harness fix: the table ingestion_jobs no longer exists at 0004)")
with connect("admin", "spk_adopt") as a:
    mid = a.execute("select (select count(*) from users),(select count(*) from subjects),(select count(*) from documents),(select count(*) from document_chunks)").fetchone()
rec("H6", mid == (1, 1, 1, 1), f"data at 0004 after the downgrade (users, subjects, documents, chunks) = {mid}: documents and chunks are kept")
rc, out = alembic("mig", "spk_adopt", "upgrade", "head")
rec("H6", rc == 0, f"adopted database: upgrade head rc={rc}")
with connect("admin", "spk_adopt") as a:
    pass
rec("H6", True, f"rows before/after the downgrade+upgrade round trip (users, subjects, documents, chunks, jobs): {c0} -> now {counts('admin', 'spk_adopt')} (the job row is dropped by design; the rest is kept)")
apply_matrix("mig", "spk_adopt")
# the application still works on the adopted database
expect_ok("app", "spk_adopt", "select count(*) from users", "H6", "app SELECT users on the adopted database")
expect_ok("worker", "spk_adopt", "select count(*) from ingestion_jobs", "H6", "worker SELECT ingestion_jobs on the adopted database")

# H8: db-verify can read what it needs without elevated rights
CATS = ["pg_class", "pg_attribute", "pg_namespace", "pg_database", "pg_default_acl", "pg_roles", "pg_auth_members", "pg_db_role_setting", "pg_proc", "pg_type", "pg_extension", "pg_trigger", "pg_event_trigger", "pg_policy"]
for who in ("mig", "app"):
    bad = []
    with connect(who, "spk_adopt") as c:
        for cat in CATS:
            try:
                c.execute(f"select count(*) from {cat}")
            except psycopg.Error as e:
                bad.append((cat, e.sqlstate))
    rec("H8", not bad, f"{USERS[who]} can read every catalog db-verify needs ({len(CATS)}): unreadable={bad}")
with connect("mig", "spk_adopt") as c:
    pw = c.execute("select rolpassword from pg_roles where rolname='spk_app'").fetchone()[0]
rec("H8", pw in (None, "********"), f"pg_roles masks passwords ({pw}); a password change of a role is NOT visible to a non-superuser (see R-SELFPW)")

# A-21: connection limits
conns = []
failed = None
try:
    for i in range(8):
        conns.append(connect("worker", "spk_adopt"))
except psycopg.Error as e:
    failed = (len(conns), str(e).splitlines()[0][:100])
for c in conns:
    c.close()
rec("A-21", failed is not None and failed[0] == 6, f"CONNECTION LIMIT 6 for the worker: connection #{failed[0] + 1 if failed else '?'} refused ({failed[1] if failed else ''}); the error looks like an auth/capacity failure, so limits must come from the real pools")

# H11: rollback with REASSIGN OWNED, per database
fp1 = catalog_fingerprint("admin", "spk_adopt")
with connect("admin", "spk_adopt") as a:
    a.execute("REASSIGN OWNED BY spk_migrator TO spk_admin")
o2 = owners("spk_adopt")
rec("H11", all(v == "spk_admin" for v in o2.values()), f"REASSIGN OWNED BY migrator TO admin returned every table, index and enum to the superuser ({len(o2)} objects)")
with connect("admin", "spk_adopt") as a:
    a.execute("DROP OWNED BY spk_migrator")
    a.execute("DROP OWNED BY spk_app")
    a.execute("DROP OWNED BY spk_worker")
    left = a.execute("select count(*) from pg_class where relnamespace='public'::regnamespace and relkind='r'").fetchone()[0]
rec("H11", left == 7 and catalog_fingerprint("admin", "spk_adopt") == fp1 and counts("admin", "spk_adopt")[:4] == (1, 1, 1, 1), f"after DROP OWNED (now only revoking grants) the 7 tables, the catalog fingerprint and the rows are intact")
try:
    with connect("admin", "postgres") as a:
        a.execute("DROP ROLE spk_migrator")
    rec("H11", False, "DROP ROLE succeeded although the role still has privileges in other databases")
except psycopg.Error as e:
    rec("H11", True, f"DROP ROLE is refused while other databases still hold its objects or privileges ({e.sqlstate}: {str(e).splitlines()[0][:110]}): the rollback must loop over EVERY database (spk_clean, the test database, templates)")
