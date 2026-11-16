"""A-14 (test layer vs drop_everything) and the adoption trap REASSIGN OWNED BY <superuser> (last, destructive for the disposable cluster)."""
import psycopg

from common import *  # noqa: F401,F403

DB = "spk_trap"
# ---- A-14: what tests/db_support.drop_everything does, on a database prepared for the roles
with connect("admin", DB) as a:
    acl_before = a.execute("select nspacl::text from pg_namespace where nspname='public'").fetchone()[0]
    a.execute("DROP SCHEMA public CASCADE")
    a.execute("CREATE SCHEMA public")
    a.execute("DROP EXTENSION IF EXISTS vector CASCADE")
    acl_after = a.execute("select nspacl::text from pg_namespace where nspname='public'").fetchone()[0]
    usage = a.execute("select has_schema_privilege('spk_app','public','USAGE'), has_schema_privilege('spk_migrator','public','CREATE')").fetchone()
    ext = a.execute("select count(*) from pg_extension where extname='vector'").fetchone()[0]
rec("A-14", usage == (False, False) and ext == 0, f"after drop_everything the schema ACL goes from {acl_before} to {acl_after}; roles keep USAGE/CREATE = {usage}; vector extension present = {ext}: a role-bound test layer must rebuild schema, ACL and extension itself before running Alembic as the migrator")
rc, out = alembic("mig", DB, "upgrade", "head")
rec("A-14", rc != 0, f"Alembic as the migrator on that database fails (rc={rc}): {last_line(out)}")
with connect("admin", DB) as a:
    a.execute("GRANT USAGE ON SCHEMA public TO spk_app, spk_worker, spk_migrator")
    a.execute("GRANT CREATE ON SCHEMA public TO spk_migrator")
    a.execute("CREATE EXTENSION vector")
rc, out = alembic("mig", DB, "upgrade", "head")
rec("A-14", rc == 0, f"after the admin step (schema ACL + extension) Alembic as the migrator works again (rc={rc})")
# test-role hygiene: prefix guard and sweep
with connect("admin", "postgres") as a:
    leftovers = [r[0] for r in a.execute("select rolname from pg_roles where rolname like 'spk\\_%' order by 1").fetchall()]
rec("A-14", len(leftovers) >= 4, f"roles of this spike left in the cluster (the sweep by prefix would remove them before each run): {leftovers}")

# ---- adoption trap: REASSIGN OWNED BY the superuser moves the databases too
with connect("admin", "postgres") as a:
    before = dict(a.execute("select datname, pg_get_userbyid(datdba) from pg_database where datname like 'spk\\_%' or datname='postgres'").fetchall())
    a.execute("REASSIGN OWNED BY spk_admin TO spk_migrator")
    after = dict(a.execute("select datname, pg_get_userbyid(datdba) from pg_database where datname like 'spk\\_%' or datname='postgres'").fetchall())
moved = [d for d in before if before[d] != after[d]]
rec("ADOPT", len(moved) > 0, f"CONFIRMED: `REASSIGN OWNED BY <superuser> TO migrator` moved the OWNERSHIP OF DATABASES too: {moved}; adoption must use explicit ALTER TABLE/TYPE ... OWNER TO")
