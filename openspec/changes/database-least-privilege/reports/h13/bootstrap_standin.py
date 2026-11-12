"""STAND-IN for the planned `db-bootstrap` (it does not exist yet). Same behaviour that the spec requires, as a one-shot Compose service:
idempotent, administrator, search_path = pg_catalog, role work from `postgres`, SCRAM verifiers computed by the client, RESET ALL before the
role settings, PUBLIC closed on every database, schema ACL, extension, default privileges. Prints no password and no verifier."""
import os
import sys

import psycopg
from psycopg import sql

ADMIN = os.environ["POSTGRES_USER"]
PW_ADMIN = os.environ["POSTGRES_PASSWORD"]
DB = os.environ.get("POSTGRES_DB", "asistenteia")
ROLES = {
    "asistente_migrator": os.environ["PW_MIG"],
    "asistente_app": os.environ["PW_APP"],
    "asistente_worker": os.environ["PW_WORKER"],
}
LIMITS = {"asistente_migrator": 4, "asistente_app": 20, "asistente_worker": 6}
ATTR = "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
OPTS = "-c search_path=pg_catalog"


def connect(dbname):
    return psycopg.connect(f"postgresql://{ADMIN}:{PW_ADMIN}@db:5432/{dbname}", autocommit=True, options=OPTS)


done = []
with connect("postgres") as c:
    for role, pw in ROLES.items():
        verifier = c.pgconn.encrypt_password(pw.encode(), role.encode(), b"scram-sha-256").decode()
        exists = c.execute("select 1 from pg_catalog.pg_roles where rolname = %s", (role,)).fetchone()
        verb = "ALTER" if exists else "CREATE"
        c.execute(sql.SQL(verb + " ROLE {} " + ATTR + " CONNECTION LIMIT {} PASSWORD {}").format(sql.Identifier(role), sql.Literal(LIMITS[role]), sql.Literal(verifier)))
        c.execute(sql.SQL("ALTER ROLE {} RESET ALL").format(sql.Identifier(role)))
        if role != "asistente_migrator":
            c.execute(sql.SQL("ALTER ROLE {} SET search_path = pg_catalog, public").format(sql.Identifier(role)))
        done.append(verb)
    c.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(DB)))
    for role in ROLES:
        c.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(DB), sql.Identifier(role)))
    others = [r[0] for r in c.execute("select datname from pg_catalog.pg_database where datname <> %s", (DB,)).fetchall()]
    for other in others:
        c.execute(sql.SQL("REVOKE CONNECT, TEMPORARY ON DATABASE {} FROM PUBLIC").format(sql.Identifier(other)))
with connect(DB) as c:
    c.execute("CREATE EXTENSION IF NOT EXISTS vector")
    c.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    c.execute("GRANT USAGE ON SCHEMA public TO asistente_app, asistente_worker, asistente_migrator")
    c.execute("GRANT CREATE ON SCHEMA public TO asistente_migrator")
    c.execute("ALTER DEFAULT PRIVILEGES FOR ROLE asistente_migrator REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC")
print(f"bootstrap done: {len(done)} roles ({','.join(sorted(set(done)))}); closed databases: {len(others)}", flush=True)
sys.exit(0)
