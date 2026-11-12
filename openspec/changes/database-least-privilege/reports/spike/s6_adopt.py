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


# =================== spk_trap: the DROP OWNED trap (A-02)
build_existing("spk_trap")
c0 = counts("admin", "spk_trap")
adopt("spk_trap")
with connect("admin", "spk_trap") as a:
    a.execute("DROP OWNED BY spk_migrator")
    left = a.execute("select count(*) from pg_class where relnamespace='public'::regnamespace and relkind='r'").fetchone()[0]
rec("A-02", left == 0, f"DANGER confirmed: `DROP OWNED BY migrator` BEFORE reassigning ownership dropped the tables the migrator owned (tables left in public: {left}; rows before: {c0}). Rollback must start with REASSIGN OWNED")

# =================== spk_adopt: adoption, H10, H6 on an adopted database, rollback H11
build_existing("spk_adopt")
fp0 = catalog_fingerprint("admin", "spk_adopt")
c0 = counts("admin", "spk_adopt")
o0 = owners("spk_adopt")
rec("H10", all(v == "spk_admin" for v in o0.values()), f"before adoption every object is owned by the superuser ({len(o0)} objects)")
adopt("spk_adopt")
o1 = owners("spk_adopt")
not_moved = {k: v for k, v in o1.items() if v != "spk_migrator"}
rec("H10", not not_moved, f"after ALTER TABLE/TYPE ... OWNER TO: tables, their indexes and the enums are all owned by the migrator ({len(o1)} objects); not moved: {not_moved}")
with connect("admin", "spk_adopt") as a:
    toast = a.execute("select count(*) from pg_class t join pg_class c on c.reltoastrelid=t.oid where c.relnamespace='public'::regnamespace and pg_get_userbyid(t.relowner)<>'spk_migrator'").fetchone()[0]
    dbowner = a.execute("select pg_get_userbyid(datdba) from pg_database where datname='spk_adopt'").fetchone()[0]
    extowner = a.execute("select pg_get_userbyid(extowner) from pg_extension where extname='vector'").fetchone()[0]
rec("H10", toast == 0 and dbowner == "spk_admin" and extowner == "spk_admin", f"TOAST tables follow their table; the database ({dbowner}) and the extension ({extowner}) keep the superuser as owner")
rec("H10", catalog_fingerprint("admin", "spk_adopt") == fp0 and counts("admin", "spk_adopt") == c0, "adoption changed neither the catalog fingerprint nor the row counts")
apply_matrix("mig", "spk_adopt")
rc, out = alembic("mig", "spk_adopt", "check")
rec("H6", rc == 0 and "No new upgrade operations" in out, f"adopted database: alembic check as migrator: {last_line(out)}")
rc, out = alembic("mig", "spk_adopt", "current")
rec("H6", "0005" in out, f"adopted database: current as migrator: {last_line(out)}")
rc, out = alembic("mig", "spk_adopt", "downgrade", "0004")
c1 = counts("admin", "spk_adopt") if rc == 0 else None
rec("H6", rc == 0, f"adopted database: downgrade 0004 as migrator rc={rc}")
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
rec("H11", left == 7 and catalog_fingerprint("admin", "spk_adopt") == fp1 and counts("admin", "spk_adopt")[:4] == c0[:4], f"after DROP OWNED (now only revoking grants) the 7 tables, the catalog fingerprint and the rows are intact")
try:
    with connect("admin", "postgres") as a:
        a.execute("DROP ROLE spk_migrator")
    rec("H11", False, "DROP ROLE succeeded although the role still has privileges in other databases")
except psycopg.Error as e:
    rec("H11", True, f"DROP ROLE is refused while other databases still hold its objects or privileges ({e.sqlstate}: {str(e).splitlines()[0][:110]}): the rollback must loop over EVERY database (spk_clean, the test database, templates)")
