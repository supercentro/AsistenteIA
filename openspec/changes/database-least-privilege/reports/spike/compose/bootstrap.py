"""Idempotent bootstrap emulation (superuser): roles, database, hardening, extension. Runs as a one-shot Compose service."""
import os
import sys

import psycopg
from psycopg import sql

HOST = "db"
ADMIN = ("spk_admin", os.environ["POSTGRES_PASSWORD"])
ROLES = {"cs_migrator": os.environ["PW_MIG"], "cs_app": os.environ["PW_APP"], "cs_worker": os.environ["PW_WORKER"]}
DB = "cs_db"
ATTR = "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"

admin = psycopg.connect(f"postgresql://{ADMIN[0]}:{ADMIN[1]}@{HOST}:5432/postgres", autocommit=True, options="-c search_path=pg_catalog")
created = []
for role, pw in ROLES.items():
    verifier = admin.pgconn.encrypt_password(pw.encode(), role.encode(), b"scram-sha-256").decode()
    exists = admin.execute("select 1 from pg_roles where rolname=%s", (role,)).fetchone()
    verb = "ALTER" if exists else "CREATE"
    admin.execute(sql.SQL(verb + " ROLE {} " + ATTR + " PASSWORD {}").format(sql.Identifier(role), sql.Literal(verifier)))
    admin.execute(sql.SQL("ALTER ROLE {} RESET ALL").format(sql.Identifier(role)))
    if role != "cs_migrator":
        admin.execute(sql.SQL("ALTER ROLE {} SET search_path = pg_catalog, public").format(sql.Identifier(role)))
    created.append((verb, role))
if not admin.execute("select 1 from pg_database where datname=%s", (DB,)).fetchone():
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB)))
admin.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(DB)))
for role in ROLES:
    admin.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(DB), sql.Identifier(role)))
for other in ("postgres", "template1"):
    admin.execute(sql.SQL("REVOKE CONNECT, TEMPORARY ON DATABASE {} FROM PUBLIC").format(sql.Identifier(other)))
with psycopg.connect(f"postgresql://{ADMIN[0]}:{ADMIN[1]}@{HOST}:5432/{DB}", autocommit=True, options="-c search_path=pg_catalog") as c:
    c.execute("CREATE EXTENSION IF NOT EXISTS vector")
    c.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    c.execute("GRANT USAGE ON SCHEMA public TO cs_app, cs_worker, cs_migrator")
    c.execute("GRANT CREATE ON SCHEMA public TO cs_migrator")
    c.execute("ALTER DEFAULT PRIVILEGES FOR ROLE cs_migrator REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC")
print("bootstrap done:", created, flush=True)
sys.exit(0)
