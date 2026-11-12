from common import *
import psycopg

# ---------- H5: CREATE EXTENSION IF NOT EXISTS as a non-superuser
rc, out = alembic("mig", "spk_noext", "upgrade", "head")
rec("H5", rc != 0 and "permission denied" in out.lower(), f"extension missing + migrator: 0001 fails (rc={rc}): {last_line(out)}")
rc, out = alembic("mig", "spk_clean", "upgrade", "head")
rec("H5", rc == 0, f"extension pre-created by the admin + migrator: `CREATE EXTENSION IF NOT EXISTS` is a no-op, upgrade head rc={rc}")
rc, out = alembic("mig", "spk_clean", "current")
rec("H6", "0005" in out, f"current as migrator: {last_line(out)}")
rc, out = alembic("mig", "spk_clean", "check")
rec("H6", rc == 0 and "No new upgrade operations" in out, f"alembic check as migrator: {last_line(out)}")
rc, out = alembic("mig", "spk_clean", "downgrade", "0004")
rec("H6", rc == 0, f"downgrade 0004 as migrator rc={rc}")
rc, out = alembic("mig", "spk_clean", "upgrade", "head")
rec("H6", rc == 0, f"upgrade head again rc={rc}")
rc, out = alembic("mig", "spk_clean", "downgrade", "base")
rec("A-13", rc != 0, f"downgrade base as migrator fails (DROP EXTENSION needs ownership): {last_line(out)}")
rc, out = alembic("mig", "spk_clean", "current")
rec("A-13", "0005" in out, f"after the failed base downgrade the database is still at 0005 (transactional DDL): {last_line(out)}")
# ---------- ownership as created by the migrator
o = owners("spk_clean")
rec("H10", all(v == "spk_migrator" for k, v in o.items()), f"clean database: every table, index and enum owned by the migrator ({len(o)} objects)")

# ---------- A-08: schema USAGE grant by the migrator (it does not own the schema)
with connect("admin", "spk_clean") as a:
    a.execute("REVOKE USAGE ON SCHEMA public FROM spk_worker")
try:
    with connect("mig", "spk_clean") as c:
        c.execute("GRANT USAGE ON SCHEMA public TO spk_worker")
except psycopg.Error as e:
    rec("A-08", True, f"GRANT USAGE ON SCHEMA by migrator raised {e.sqlstate}")
with connect("admin", "spk_clean") as a:
    has = a.execute("select has_schema_privilege('spk_worker','public','USAGE')").fetchone()[0]
    rec("A-08", has is False, f"after the migrator's GRANT USAGE ON SCHEMA public the worker has USAGE = {has} (the migrator cannot hand out schema privileges; the bootstrap must)")
    a.execute("GRANT USAGE ON SCHEMA public TO spk_worker")

# ---------- A-07: grants vanish when the table is recreated
apply_matrix("mig", "spk_clean")
with connect("admin", "spk_clean") as a:
    q = "select has_table_privilege('spk_worker','ingestion_jobs','SELECT'), has_column_privilege('spk_worker','ingestion_jobs','payload','UPDATE')"
    before = a.execute(q).fetchone()
rc, _ = alembic("mig", "spk_clean", "downgrade", "0004")
rc2, _ = alembic("mig", "spk_clean", "upgrade", "head")
with connect("admin", "spk_clean") as a:
    after = a.execute("select to_regclass('ingestion_jobs') is not null, has_column_privilege('spk_worker','ingestion_jobs','payload','UPDATE'), has_column_privilege('spk_worker','ingestion_jobs','payload','SELECT')").fetchone()
rec("A-07", before[1] is True and after[0] is True and after[1] is False and after[2] is False, f"worker could UPDATE payload before={before[1]}; after downgrade 0004 + upgrade head the table exists={after[0]} and the worker's UPDATE={after[1]} SELECT={after[2]}: the grants are lost with the table")
apply_matrix("mig", "spk_clean")
with connect("admin", "spk_clean") as a:
    again = a.execute("select has_column_privilege('spk_worker','ingestion_jobs','payload','UPDATE')").fetchone()[0]
rec("A-07", again is True, f"re-running the grants step restores them (idempotent GRANT): {again}")
# idempotence of the matrix
apply_matrix("mig", "spk_clean")
rec("grants", True, "matrix applied three times without error (GRANT is idempotent)")
