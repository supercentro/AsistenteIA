from common import *
import psycopg
from psycopg import sql

admin = connect("admin", "postgres")
ATTR = "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
LIM = {"mig": 4, "app": 20, "worker": 6}
# ---- H9: SCRAM verifier computed in the client; the clear text never goes to the server
for who in ("mig", "app", "worker"):
    v = admin.pgconn.encrypt_password(PW[who.upper() if who != "mig" else "MIG"].encode(), USERS[who].encode(), b"scram-sha-256").decode()
    assert v.startswith("SCRAM-SHA-256$")
    admin.execute(sql.SQL("CREATE ROLE {} " + ATTR + " CONNECTION LIMIT {} PASSWORD {}").format(sql.Identifier(USERS[who]), sql.Literal(LIM[who]), sql.Literal(v)))
with connect("admin", "postgres") as c:
    rows = c.execute("select rolname, left(rolpassword,14), rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolconnlimit from pg_authid where rolname like 'spk\_%' and rolname<>'spk_admin' order by 1").fetchall()
rec("H9", all(r[1] == "SCRAM-SHA-256$" and not any(r[2:7]) for r in rows), f"verifier computed with libpq encrypt_password accepted at CREATE ROLE; stored as SCRAM; attributes all false: {[(r[0], r[7]) for r in rows]}")
for who in ("mig", "app", "worker"):
    try:
        with connect(who, "postgres") as c:
            pass
        ok = False  # postgres DB is still open to PUBLIC at this point (default)
        ok = True
    except psycopg.Error as e:
        ok = False
    rec("H9", ok, f"login as {USERS[who]} with the client-computed verifier (before hardening: default PUBLIC CONNECT)")
# ---- databases
for db in ("spk_clean", "spk_adopt", "spk_noext", "spk_trap", "spk_other"):
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db)))
for db in ("spk_clean", "spk_adopt", "spk_noext", "spk_trap"):
    admin.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(db)))
    for who in ("mig", "app", "worker"):
        admin.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(db), sql.Identifier(USERS[who])))
# A-09: the other databases of the cluster (including the template) close to PUBLIC
for db in ("postgres", "template1", "spk_other"):
    admin.execute(sql.SQL("REVOKE CONNECT, TEMPORARY ON DATABASE {} FROM PUBLIC").format(sql.Identifier(db)))
# per-role settings (defaults, not controls)
for who in ("app", "worker"):
    admin.execute(sql.SQL("ALTER ROLE {} SET search_path = pg_catalog, public").format(sql.Identifier(USERS[who])))
# schema level, per database
for db in ("spk_clean", "spk_noext", "spk_trap"):
    with connect("admin", db) as c:
        c.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        c.execute("GRANT USAGE ON SCHEMA public TO spk_app, spk_worker, spk_migrator")
        c.execute("GRANT CREATE ON SCHEMA public TO spk_migrator")
        if db != "spk_noext":
            c.execute("CREATE EXTENSION vector")
        c.execute("ALTER DEFAULT PRIVILEGES FOR ROLE spk_migrator REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC")
rec("setup", True, "roles, databases and hardening created (spk_clean, spk_noext, spk_trap prepared; spk_adopt and spk_other left for later)")
# A-09 tests
for db in ("postgres", "template1", "spk_other"):
    for who in ("app", "worker", "mig"):
        expect_error(who, db, "select 1", "A-09", f"{USERS[who]} connect to {db}", "42501")
for who in ("app", "worker", "mig"):
    expect_ok(who, "spk_clean", "select current_user", "A-09", f"{USERS[who]} connect to the application DB")
expect_error("app", "spk_clean", "create temp table t(x int)", "A-09", "temp table in the application DB", "42501")
