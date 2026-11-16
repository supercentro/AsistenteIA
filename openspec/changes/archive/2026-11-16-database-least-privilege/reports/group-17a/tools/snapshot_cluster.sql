-- Read-only description of the CLUSTER (roles, databases, settings) as `key|value` lines (group 17A).
--
--   docker exec -i <container> psql -U <admin> -d postgres -At -F '|' -v ON_ERROR_STOP=1 -f - < snapshot_cluster.sql
--
-- No password and no verifier is selected. `system_identifier` and `server` identify the server and
-- are removed by the comparison tool; everything else must be equal between a source and a restored
-- copy, and between the state before an operation and the state after its rollback.
SET default_transaction_read_only = on;

SELECT 'server', version();
SELECT 'system_identifier', system_identifier FROM pg_control_system();

SELECT 'role', rolname || ' super=' || rolsuper || ' createrole=' || rolcreaterole || ' createdb=' || rolcreatedb
       || ' login=' || rolcanlogin || ' replication=' || rolreplication || ' bypassrls=' || rolbypassrls
       || ' connlimit=' || rolconnlimit || ' inherit=' || rolinherit || ' config=' || coalesce(rolconfig::text, '(none)')
FROM pg_roles WHERE rolname !~ '^pg_' ORDER BY rolname;

SELECT 'membership', pg_get_userbyid(roleid) || ' contains ' || pg_get_userbyid(member)
FROM pg_auth_members WHERE pg_get_userbyid(roleid) !~ '^pg_' ORDER BY 2;

SELECT 'database', datname || ' owner=' || pg_get_userbyid(datdba) || ' allowconn=' || datallowconn
       || ' istemplate=' || datistemplate || ' acl=' || coalesce(datacl::text, '(default)')
FROM pg_database ORDER BY datname;

SELECT 'role_setting', coalesce((SELECT datname FROM pg_database WHERE oid = setdatabase), '(all databases)')
       || ' ' || coalesce((SELECT rolname FROM pg_roles WHERE oid = setrole), '(all roles)') || ' ' || setconfig::text
FROM pg_db_role_setting ORDER BY 2;

SELECT 'prepared_transactions', count(*) FROM pg_prepared_xacts;
SELECT 'replication_slots', count(*) FROM pg_replication_slots;
SELECT 'sessions', coalesce(usename, '?') || ' on ' || coalesce(datname, '-') || ' x' || count(*)
FROM pg_stat_activity WHERE backend_type = 'client backend' AND pid <> pg_backend_pid()
GROUP BY usename, datname ORDER BY 2;
