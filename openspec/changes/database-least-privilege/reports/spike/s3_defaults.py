from common import *
import psycopg
from psycopg import sql

admin = connect("admin", "postgres")
# ---------------- H7 / A-05: default privileges, three variants
variants = {"spk_d1": None, "spk_d2": "ALTER DEFAULT PRIVILEGES FOR ROLE spk_migrator IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC",
            "spk_d3": "ALTER DEFAULT PRIVILEGES FOR ROLE spk_migrator REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"}
res = {}
for db, stmt in variants.items():
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db)))
    admin.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO spk_migrator, spk_app, spk_worker").format(sql.Identifier(db)))
    with connect("admin", db) as a:
        a.execute("GRANT USAGE ON SCHEMA public TO spk_app, spk_worker")
        a.execute("GRANT CREATE, USAGE ON SCHEMA public TO spk_migrator")
        a.execute("CREATE EXTENSION vector")
        if stmt:
            a.execute(stmt)
    with connect("mig", db) as m:
        m.execute("CREATE TABLE public.t_test(a int, b int)")
        m.execute("CREATE FUNCTION public.f_test() RETURNS int LANGUAGE sql AS 'select 1'")
        m.execute("CREATE TYPE public.ty_test AS ENUM ('a')")
    with connect("admin", db) as a:
        res[db] = {
            "table_acl": a.execute("select relacl::text from pg_class where relname='t_test'").fetchone()[0],
            "func_acl": a.execute("select proacl::text from pg_proc where proname='f_test'").fetchone()[0],
            "type_acl": a.execute("select typacl::text from pg_type where typname='ty_test'").fetchone()[0],
            "app_select": a.execute("select has_table_privilege('spk_app','public.t_test','SELECT')").fetchone()[0],
            "app_exec": a.execute("select has_function_privilege('spk_app','public.f_test()','EXECUTE')").fetchone()[0],
            "app_type": a.execute("select has_type_privilege('spk_app','public.ty_test','USAGE')").fetchone()[0],
        }
for db, r in res.items():
    rec("H7", None, f"{db}: table_acl={r['table_acl']} func_acl={r['func_acl']} type_acl={r['type_acl']} | app: select={r['app_select']} execute={r['app_exec']} type_usage={r['app_type']}")
rec("A-05", res["spk_d1"]["app_exec"] is True and res["spk_d2"]["app_exec"] is True and res["spk_d3"]["app_exec"] is False,
    "PUBLIC EXECUTE on a new function: default=%s, per-schema REVOKE=%s (no effect), global REVOKE=%s; tables are closed by default (app select=%s) with or without the statement; types stay usable by PUBLIC (%s)" % (res["spk_d1"]["app_exec"], res["spk_d2"]["app_exec"], res["spk_d3"]["app_exec"], res["spk_d1"]["app_select"], res["spk_d3"]["app_type"]))
rec("A-05", res["spk_d1"]["app_select"] is False, "new tables are owner-only by default: fail closed without any ALTER DEFAULT PRIVILEGES")

# ---------------- H12: column vs table level REVOKE
with connect("mig", "spk_d1") as m:
    m.execute("GRANT UPDATE (a) ON t_test TO spk_app")
    m.execute("GRANT UPDATE ON t_test TO spk_app")
    m.execute("REVOKE UPDATE (a) ON t_test FROM spk_app")
    st1 = m.execute("select has_column_privilege('spk_app','t_test','a','UPDATE'), has_column_privilege('spk_app','t_test','b','UPDATE')").fetchone()
    m.execute("REVOKE UPDATE ON t_test FROM spk_app")
    st2 = m.execute("select has_column_privilege('spk_app','t_test','a','UPDATE'), has_column_privilege('spk_app','t_test','b','UPDATE')").fetchone()
    m.execute("GRANT UPDATE (a) ON t_test TO spk_app")
    m.execute("GRANT UPDATE ON t_test TO spk_app")
    m.execute("REVOKE UPDATE ON t_test FROM spk_app")
    st3 = m.execute("select has_column_privilege('spk_app','t_test','a','UPDATE')").fetchone()[0]
rec("H12", st1 == (True, True) and st2 == (False, False) and st3 is False,
    f"column-level REVOKE does not remove a table-level grant (a,b still updatable: {st1}); table-level REVOKE removes the table grant and the column grants (a,b: {st2}; with both granted: {st3}). db-grants must REVOKE at table level first, then GRANT columns")

# ---------------- A-10 / A-11 / A-12: objects planted in public by the table owner
with connect("mig", "spk_d1") as m:
    m.execute("CREATE FUNCTION public.lower(text) RETURNS text LANGUAGE sql AS $$select 'HACKED'::text$$")
    m.execute("CREATE TABLE public.audit_log(who text)")
    m.execute("CREATE FUNCTION public.log_who() RETURNS trigger LANGUAGE plpgsql AS $$begin insert into public.audit_log values (current_user); return new; end$$")
    m.execute("CREATE TRIGGER trg AFTER INSERT ON public.t_test FOR EACH ROW EXECUTE FUNCTION public.log_who()")
with connect("app", "spk_d1") as c:
    safe = c.execute("select lower('ABC')").fetchone()[0]
    c.execute("SET search_path = public, pg_catalog")
    unsafe = c.execute("select lower('ABC')").fetchone()[0]
rec("A-10", safe == "abc" and unsafe == "HACKED", f"with search_path=pg_catalog,public the app gets '{safe}'; with public first a function planted in public by the migrator wins ('{unsafe}'): runtime roles must use pg_catalog first")
with connect("admin", "spk_d1") as a:
    a.execute("SET search_path = public, pg_catalog")
    unsafe_admin = a.execute("select lower('ABC')").fetchone()[0]
    a.execute("SET search_path = pg_catalog")
    a.execute("INSERT INTO public.t_test VALUES (1,1)")
    who = a.execute("select string_agg(who, ',') from public.audit_log").fetchone()[0]
rec("A-11", unsafe_admin == "HACKED" and who == "spk_admin", f"a superuser with the default search_path also runs the planted function ('{unsafe_admin}'), and a trigger planted by the owner ran as the role doing the DML ({who}): the superuser must not touch application tables/objects and must use search_path=pg_catalog")
with connect("admin", "spk_d1") as a:
    foreign = a.execute("""select 'func '||p.proname from pg_proc p where p.pronamespace='public'::regnamespace and not exists (select 1 from pg_depend d where d.objid=p.oid and d.deptype='e')
        union all select 'trigger '||tgname from pg_trigger where not tgisinternal
        union all select 'type '||t.typname from pg_type t where t.typnamespace='public'::regnamespace and t.typtype in ('e','d','c') and t.typname not like '\_%' and t.typrelid=0 and not exists (select 1 from pg_depend d where d.objid=t.oid and d.deptype='e')""").fetchall()
rec("A-12", len(foreign) >= 3, f"the pre-update/db-verify query for non-extension objects in public finds the planted ones: {[r[0] for r in foreign]}")
expect_error("mig", "spk_d1", "ALTER EXTENSION vector UPDATE", "A-12", "migrator cannot ALTER EXTENSION vector UPDATE (not the owner)", "42501")
with connect("admin", "spk_d1") as a:
    try:
        a.execute("ALTER EXTENSION vector UPDATE")
        rec("H14", True, "admin ALTER EXTENSION vector UPDATE succeeds with migrator-owned objects in public (already at the latest version: no-op; real updates need the pre-check above)")
    except psycopg.Error as e:
        rec("H14", False, str(e)[:120])
