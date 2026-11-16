-- Read-only description of ONE database as `key|value` lines in a deterministic order (group 17A).
--
--   docker exec -i <container> psql -U <admin> -d <database> -At -F '|' -v ON_ERROR_STOP=1 -f - < snapshot_db.sql
--
-- It changes nothing (the session is read only) and prints no secret: no password, no verifier, no
-- connection string. The lines are compared with `diff` between a source and a restored copy, or
-- before and after an operation. Lines that identify a server rather than describe a database
-- (`server`, `database_oid`) are filtered out by the comparison tool.
SET default_transaction_read_only = on;

SELECT 'database', current_database();
SELECT 'server', current_setting('server_version');
SELECT 'database_owner', pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database();
SELECT 'database_acl', coalesce(datacl::text, '(default)') FROM pg_database WHERE datname = current_database();
SELECT 'extension', extname || ' ' || extversion || ' owner=' || pg_get_userbyid(extowner)
       || ' schema=' || (SELECT nspname FROM pg_namespace WHERE oid = extnamespace)
FROM pg_extension ORDER BY extname;
SELECT 'revision', CASE WHEN to_regclass('public.alembic_version') IS NULL THEN '(no alembic_version)'
       ELSE (xpath('/row/v/text()', query_to_xml('select version_num as v from public.alembic_version', false, true, '')))[1]::text END;
SELECT 'schema_public', pg_get_userbyid(nspowner) || ' acl=' || coalesce(nspacl::text, '(default)')
FROM pg_namespace WHERE nspname = 'public';

SELECT 'table', c.relname || ' owner=' || pg_get_userbyid(c.relowner)
       || ' acl=' || coalesce(c.relacl::text, '(default)') || ' rls=' || c.relrowsecurity
FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r', 'p')
ORDER BY c.relname;

SELECT 'column', c.relname || '.' || a.attname || ' ' || format_type(a.atttypid, a.atttypmod)
       || ' notnull=' || a.attnotnull
       || ' default=' || coalesce(pg_get_expr(d.adbin, d.adrelid), '(none)')
       || ' acl=' || coalesce(a.attacl::text, '(none)')
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r', 'p') AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY c.relname, a.attnum;

SELECT 'index', indexname || ' ' || indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY indexname;

SELECT 'constraint', conrelid::regclass::text || ' ' || conname || ' ' || pg_get_constraintdef(oid)
FROM pg_constraint WHERE connamespace = 'public'::regnamespace
ORDER BY conrelid::regclass::text, conname;

SELECT 'type', t.typname || ' owner=' || pg_get_userbyid(t.typowner) || ' acl=' || coalesce(t.typacl::text, '(default)')
       || ' labels=' || (SELECT string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder) FROM pg_enum e WHERE e.enumtypid = t.oid)
FROM pg_type t WHERE t.typnamespace = 'public'::regnamespace AND t.typtype = 'e'
ORDER BY t.typname;

SELECT 'sequence', c.relname || ' owner=' || pg_get_userbyid(c.relowner) || ' acl=' || coalesce(c.relacl::text, '(default)')
FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'S' ORDER BY c.relname;

SELECT 'default_acl', pg_get_userbyid(defaclrole) || ' ' || defaclobjtype::text || ' ' || defaclacl::text
FROM pg_default_acl ORDER BY 2;

SELECT 'foreign_objects', count(*) FROM pg_proc p
WHERE p.pronamespace = 'public'::regnamespace
  AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e');

SELECT 'rows', c.relname || '=' ||
       (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', 'public', c.relname), false, true, '')))[1]::text
FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r', 'p')
ORDER BY c.relname;

SELECT 'sessions_on_this_database', count(*) FROM pg_stat_activity
WHERE datname = current_database() AND pid <> pg_backend_pid() AND backend_type = 'client backend';
