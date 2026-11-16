"""Spike 2: closes the evidence gaps and the new attacks raised by the second review (B-01, B-03, B-05, B-06, B-10, H1x)."""
import threading
import time
import uuid

import psycopg
from psycopg import sql

from common import *  # noqa: F401,F403

# ================= B-01: search_path with a MORE SPECIFIC signature and with an operator
D = "spk_d1"
with connect("mig", D) as m:
    m.execute("CREATE FUNCTION public.lower(varchar) RETURNS text LANGUAGE sql AS $$select 'HACKED2'::text$$")
    m.execute("CREATE FUNCTION public.vc_eq(varchar, varchar) RETURNS boolean LANGUAGE sql AS $$select false$$")
    m.execute("CREATE OPERATOR public.= (LEFTARG = varchar, RIGHTARG = varchar, FUNCTION = public.vc_eq)")
res = {}
for who in ("admin", "app"):
    with connect(who, D) as c:
        for label, path in (("pg_catalog,public", "pg_catalog, public"), ("pg_catalog only", "pg_catalog")):
            c.execute(f"SET search_path = {path}")
            res[(who, label)] = (
                c.execute("select lower('ABC'::varchar)").fetchone()[0],
                c.execute("select ('a'::varchar = 'a'::varchar)").fetchone()[0],
            )
rec("B-01", res[("admin", "pg_catalog,public")] == ("HACKED2", False) and res[("admin", "pg_catalog only")] == ("abc", True),
    f"superuser session: with `pg_catalog, public` a planted lower(varchar) and an operator =(varchar,varchar) in public WIN even though pg_catalog comes first {res[('admin','pg_catalog,public')]}; with `pg_catalog` only they are invisible {res[('admin','pg_catalog only')]}. The superuser bootstrap must use search_path = pg_catalog and qualified names")
rec("B-01", res[("app", "pg_catalog,public")][0] == "HACKED2", f"the runtime roles need `public` for the vector type and operators, so they stay exposed to objects planted by the (trusted) migrator: {res[('app','pg_catalog,public')]}; control = migrations are code reviewed and db-verify lists foreign objects in public")
with connect("admin", D) as a:
    foreign = [r[0] for r in a.execute("""select 'func '||p.proname||'('||pg_get_function_identity_arguments(p.oid)||')' from pg_proc p where p.pronamespace='public'::regnamespace and not exists (select 1 from pg_depend d where d.objid=p.oid and d.deptype='e')
        union all select 'operator '||o.oprname from pg_operator o where o.oprnamespace='public'::regnamespace and not exists (select 1 from pg_depend d where d.objid=o.oid and d.deptype='e')""").fetchall()]
rec("B-01", any(x.startswith("operator") for x in foreign) and any("lower(character varying)" in x for x in foreign), f"db-verify query must also list operators and exact signatures; it finds: {foreign}")

# ================= B-03: revoke-then-grant atomicity under a concurrent session
DB = "spk_clean"
errors = {"n": 0, "ok": 0}
stop = threading.Event()


def poll():
    with connect("app", DB) as c:
        while not stop.is_set():
            try:
                c.execute("select count(*) from users").fetchone()
                errors["ok"] += 1
            except psycopg.errors.InsufficientPrivilege:
                errors["n"] += 1
            time.sleep(0.002)


def regrant(atomic: bool, loops: int = 60):
    with connect("mig", DB) as m:
        for _ in range(loops):
            if atomic:
                with m.transaction():
                    m.execute("REVOKE ALL ON users FROM spk_app")
                    m.execute("GRANT SELECT, INSERT ON users TO spk_app")
                    m.execute("GRANT UPDATE (consent_version, consent_accepted_at) ON users TO spk_app")
            else:
                m.execute("REVOKE ALL ON users FROM spk_app")
                m.execute("GRANT SELECT, INSERT ON users TO spk_app")
                m.execute("GRANT UPDATE (consent_version, consent_accepted_at) ON users TO spk_app")
            time.sleep(0.003)


out = {}
for atomic in (False, True):
    errors.update(n=0, ok=0)
    stop.clear()
    t = threading.Thread(target=poll)
    t.start()
    regrant(atomic)
    stop.set()
    t.join()
    out[atomic] = (errors["n"], errors["ok"])
rec("B-03", out[False][0] > 0 and out[True][0] == 0, f"concurrent reader as the app role during 60 revoke+grant cycles: non-atomic (autocommit) -> {out[False][0]} permission errors of {out[False][0] + out[False][1]} reads; one transaction per cycle -> {out[True][0]} errors of {out[True][0] + out[True][1]} reads. db-grants must be transactional (GRANT/REVOKE are)")

# ================= B-05: ALTER ROLE ... SET by the role itself, RESET ALL, login probe, verifier salts
for stmt, label in (("alter role spk_app set search_path = public, pg_catalog", "ALTER ROLE self SET search_path"), ("alter role spk_app set statement_timeout = 0", "ALTER ROLE self SET statement_timeout")):
    try:
        with connect("app", DB) as c:
            c.execute(stmt)
        rec("B-05", True, f"CONFIRMED: the app role can run `{label}` and it persists for every later session")
    except psycopg.Error as e:
        rec("B-05", False, f"{label}: refused {e.sqlstate}")
with connect("admin", DB) as a:
    cfg = a.execute("select setconfig from pg_db_role_setting s join pg_roles r on r.oid=s.setrole where r.rolname='spk_app'").fetchall()
    rec("B-05", None, f"role-level settings now stored for spk_app: {cfg}")
    a.execute("ALTER ROLE spk_app RESET ALL")
    a.execute("ALTER ROLE spk_app SET search_path = pg_catalog, public")
    cfg2 = a.execute("select setconfig from pg_db_role_setting s join pg_roles r on r.oid=s.setrole where r.rolname='spk_app'").fetchall()
rec("B-05", cfg2 == [(["search_path=pg_catalog, public"],)], f"the bootstrap's `ALTER ROLE ... RESET ALL` + its own SET removes tampering: {cfg2}")
v1 = connect("admin", "postgres").pgconn.encrypt_password(PW["APP"].encode(), b"spk_app", b"scram-sha-256")
v2 = connect("admin", "postgres").pgconn.encrypt_password(PW["APP"].encode(), b"spk_app", b"scram-sha-256")
rec("B-05", v1 != v2, "two client-side verifiers of the SAME password differ (random salt): comparing stored hashes cannot detect a password change; detection must be a login probe with the expected password")
try:
    with connect("app", DB) as c:
        c.execute("alter role spk_app password 'changed-by-the-role'")
except psycopg.Error:
    pass
probe_ok = True
try:
    connect("app", DB).close()
except psycopg.Error:
    probe_ok = False
rec("B-05", probe_ok is False, "after the role changed its own password the login probe with the expected password FAILS: that is the detector")
with connect("admin", "postgres") as a:
    v = a.pgconn.encrypt_password(PW["APP"].encode(), b"spk_app", b"scram-sha-256").decode()
    a.execute(sql.SQL("ALTER ROLE spk_app PASSWORD {}").format(sql.Literal(v)))
expect_ok("app", DB, "select current_user", "B-05", "the next bootstrap run (ALTER ROLE ... PASSWORD from the env value) heals the tampering")

# ================= B-06: LOCK TABLE, direct teacher insert, chunk poisoning; B-10 negatives
with connect("admin", DB) as a:
    uid, sid, did = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    a.execute("insert into users(id,email,name,password_hash,role) values (%s,'seed@example.com','s','x','teacher')", (uid,))
    a.execute("insert into subjects(id,teacher_id,name) values (%s,%s,'s1')", (sid, uid))
    a.execute("insert into documents(id,subject_id,filename,content_type,size_bytes,status) values (%s,%s,'f.txt','text/plain',5,'pending')", (did, sid))
for who, tbl in (("app", "users"), ("app", "subjects"), ("app", "documents"), ("worker", "documents"), ("worker", "ingestion_jobs")):
    expect_error(who, DB, f"begin; lock table {tbl} in access exclusive mode", "B-06", f"{USERS[who]}: LOCK TABLE {tbl} ACCESS EXCLUSIVE (needs table-level UPDATE/DELETE/TRUNCATE; only column-level UPDATE is held)", "42501")
expect_ok("app", DB, "insert into users(id,email,name,password_hash,role) values (gen_random_uuid(),'forged-teacher@example.com','x','x','teacher')", "B-06", "app can INSERT a user with role='teacher' (the CLI shares the app role): 'teachers only by CLI' does not hold at database level")
expect_ok("worker", DB, "insert into document_chunks(document_id, subject_id, chunk_index, content, embedding) values (%s,%s,0,'poison', array_fill(0.01::real, ARRAY[384])::vector)", "B-06", "worker can INSERT a chunk for ANY existing (document, subject): cross-subject RAG poisoning is inherent to direct table access", params=(did, sid))
for who, stmt, label in (("worker", "select size_bytes from documents", "worker SELECT documents.size_bytes (ungranted column)"), ("worker", "select created_at from documents", "worker SELECT documents.created_at"), ("worker", "select error_code from documents", "worker SELECT documents.error_code (it only writes it)"), ("worker", "select 1 from document_chunks where false and content is null", "worker reads document_chunks.content in a predicate")):
    expect_error(who, DB, stmt, "B-10", label, "42501")
try:
    with connect("app", DB) as c:
        c.execute("grant select on users to spk_worker")
    with connect("admin", DB) as a:
        has = a.execute("select has_table_privilege('spk_worker','users','SELECT')").fetchone()[0]
    rec("B-10", has is False, f"app GRANT SELECT ON users TO worker: no error raised (only a warning) and no privilege granted (worker has SELECT = {has})")
except psycopg.Error as e:
    rec("B-10", True, f"app GRANT refused {e.sqlstate}")
expect_error("worker", DB, "copy public.users from program 'id'", "B-10", "worker COPY FROM PROGRAM", "42501")
with connect("admin", DB) as a:
    a.execute("delete from document_chunks")
    a.execute("delete from subjects")
    a.execute("delete from users where email in ('seed@example.com','forged-teacher@example.com')")

# ================= H1x: cascade across tables with different owners (script recorded)
D1 = "spk_d1"
with connect("admin", "postgres") as a:
    a.execute("CREATE ROLE spk_o NOLOGIN")
with connect("admin", D1) as a:
    a.execute("GRANT USAGE, CREATE ON SCHEMA public TO spk_o")
with connect("mig", D1) as m:
    m.execute("CREATE TABLE parent(id int primary key, v text)")
    m.execute("GRANT SELECT, INSERT, DELETE ON parent TO spk_app")
    m.execute("GRANT REFERENCES ON parent TO spk_o")
with connect("admin", D1) as a:
    a.execute("SET ROLE spk_o")
    a.execute("CREATE TABLE child(id int primary key, pid int references parent(id) on delete cascade)")
    a.execute("RESET ROLE")
    a.execute("GRANT INSERT ON child TO spk_worker")
with connect("app", D1) as c:
    c.execute("insert into parent values (1,'a')")
with connect("admin", D1) as a:
    a.execute("insert into child values (1, 1)")
with connect("app", D1) as c:
    c.execute("delete from parent where id=1")
with connect("admin", D1) as a:
    n = a.execute("select count(*) from child").fetchone()[0]
    a.execute("insert into parent values (2,'b')")
rec("H1x", n == 0, f"parent owned by the migrator, child owned by another role: cascade works for a role with DELETE on the parent only (child rows left {n})")
with connect("worker", D1) as c:
    c.execute("insert into child values (2, 2)")
rec("H1x", True, "FK-checked INSERT works for a role with no privilege at all on the referenced table")
expect_error("worker", D1, "insert into child values (3, 99)", "H1x", "FK violation still refused", "23503")
