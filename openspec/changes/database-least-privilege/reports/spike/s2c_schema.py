from common import *
import psycopg
with connect("admin", "spk_clean") as a:
    acl0 = a.execute("select nspacl::text from pg_namespace where nspname='public'").fetchone()[0]
    rec("A-08r", True, f"schema public ACL as left by the bootstrap so far: {acl0} (PUBLIC still has USAGE by default)")
    a.execute("REVOKE USAGE ON SCHEMA public FROM PUBLIC")
    a.execute("REVOKE USAGE ON SCHEMA public FROM spk_worker")
    has = a.execute("select has_schema_privilege('spk_worker','public','USAGE')").fetchone()[0]
    rec("A-08r", has is False, f"after REVOKE from PUBLIC and from the worker: worker USAGE = {has}")
expect_error("worker", "spk_clean", "select count(*) from ingestion_jobs", "A-08r", "worker without schema USAGE cannot even resolve the table", "42501")
try:
    with connect("mig", "spk_clean") as c:
        c.execute("GRANT USAGE ON SCHEMA public TO spk_worker")
    rec("A-08r", None, "migrator GRANT raised no error (may only be a warning)")
except psycopg.Error as e:
    rec("A-08r", True, f"migrator GRANT USAGE ON SCHEMA raised {e.sqlstate}")
with connect("admin", "spk_clean") as a:
    has = a.execute("select has_schema_privilege('spk_worker','public','USAGE')").fetchone()[0]
    rec("A-08r", has is False, f"worker USAGE after the migrator's GRANT = {has}: the migrator cannot grant schema privileges (it does not own the schema); the bootstrap must")
    a.execute("GRANT USAGE ON SCHEMA public TO spk_app, spk_worker, spk_migrator")
    a.execute("GRANT CREATE ON SCHEMA public TO spk_migrator")
    acl = a.execute("select nspacl::text from pg_namespace where nspname='public'").fetchone()[0]
    rec("A-08r", True, f"final schema ACL: {acl}")
expect_ok("worker", "spk_clean", "select count(*) from ingestion_jobs where false", "A-08r", "worker with USAGE and column SELECT can query")
