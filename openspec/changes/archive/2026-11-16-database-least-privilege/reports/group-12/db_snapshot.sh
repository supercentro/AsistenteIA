#!/usr/bin/env bash
# Read-only snapshot of the DEVELOPMENT database (change database-least-privilege, tasks 12.1/12.3).
#
#   usage: db_snapshot.sh <label>      prints the snapshot; the part between the markers DATA-BEGIN and
#                                      DATA-END is deterministic and is compared before and after.
#
# Every statement is a SELECT or SHOW, in a session where default_transaction_read_only is on
# (PGOPTIONS), executed with `docker exec` in the EXISTING container: nothing is recreated, stopped,
# granted, migrated or written. No password or connection string is printed.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
export MSYS_NO_PATHCONV=1
DB=asistenteia-db-1
sql() {
  docker exec -e PGOPTIONS="-c default_transaction_read_only=on" "$DB" sh -c \
    'psql -U "$POSTGRES_USER" -d asistenteia -X -A -t -F " | " -v ON_ERROR_STOP=1 -c "$0"' "$1"
}

echo "== snapshot: $1 ($(date -u +%FT%TZ))"
echo "container: $(docker inspect "$DB" --format '{{.State.Health.Status}}') (db), $(docker inspect asistenteia-worker-1 --format '{{.State.Health.Status}}') (worker)"
echo "session read-only: $(sql 'SHOW default_transaction_read_only')"
echo "server: $(sql 'SELECT version()' | cut -c1-60)"
echo "-- DATA-BEGIN"
echo "alembic_version: $(sql 'SELECT version_num FROM alembic_version')"
echo "extensions: $(sql "SELECT string_agg(extname || ' ' || extversion, ', ' ORDER BY extname) FROM pg_extension")"
echo "users.role default: $(sql "SELECT coalesce(pg_get_expr(d.adbin, d.adrelid), '(none)') FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum WHERE a.attrelid = 'public.users'::regclass AND a.attname = 'role'")"
echo "databases: $(sql "SELECT string_agg(datname, ', ' ORDER BY datname) FROM pg_database")"
echo "roles (without the built-in pg_*): $(sql "SELECT string_agg(rolname || CASE WHEN rolsuper THEN '(superuser)' ELSE '' END, ', ' ORDER BY rolname) FROM pg_roles WHERE rolname !~ '^pg_'")"
echo "new roles present (asistente_*, tstrole_*): $(sql "SELECT count(*) FROM pg_roles WHERE rolname ~ '^(asistente_|tstrole_)'")"
echo "databases of the tests (tstdb_*): $(sql "SELECT count(*) FROM pg_database WHERE datname ~ '^tstdb_'")"
echo "tables and owners:"
sql "SELECT relname || ' owner=' || pg_get_userbyid(relowner) || ' acl=' || coalesce(relacl::text, '(default)') FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r' ORDER BY relname" | sed 's/^/  /'
echo "row counts:"
for table in users subjects enrollments documents document_chunks ingestion_jobs; do
  echo "  $table: $(sql "SELECT count(*) FROM public.$table")"
done
echo "documents by status: $(sql "SELECT coalesce(string_agg(status::text || '=' || n, ', ' ORDER BY status::text), '(none)') FROM (SELECT status, count(*) AS n FROM public.documents GROUP BY status) s")"
echo "users by role: $(sql "SELECT coalesce(string_agg(role::text || '=' || n, ', ' ORDER BY role::text), '(none)') FROM (SELECT role, count(*) AS n FROM public.users GROUP BY role) s")"
echo "ingestion_jobs: total=$(sql 'SELECT count(*) FROM public.ingestion_jobs') with_payload=$(sql 'SELECT count(*) FROM public.ingestion_jobs WHERE payload IS NOT NULL') leased=$(sql 'SELECT count(*) FROM public.ingestion_jobs WHERE locked_by IS NOT NULL') max_attempts=$(sql 'SELECT coalesce(max(attempts), 0) FROM public.ingestion_jobs')"
test_sql() {
  docker exec -e PGOPTIONS="-c default_transaction_read_only=on" "$DB" sh -c     'psql -U "$POSTGRES_USER" -d asistenteia_test -X -A -t -F " | " -v ON_ERROR_STOP=1 -c "$0"' "$1"
}
echo "test database asistenteia_test (the one of the development cluster; the tests of this group use their own disposable clusters):"
echo "  has alembic_version: $(test_sql "SELECT to_regclass('public.alembic_version') IS NOT NULL")"
echo "  public tables: $(test_sql "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")"
echo "  new roles with privileges on it (asistente_*, tstrole_*): $(test_sql "SELECT count(*) FROM pg_roles WHERE rolname ~ '^(asistente_|tstrole_)'")"
echo "-- DATA-END"
echo "connections by role, database and state (volatile):"
sql "SELECT coalesce(usename, '(background)') || ' db=' || coalesce(datname, '-') || ' state=' || coalesce(state, '-') || ' n=' || count(*) FROM pg_stat_activity WHERE backend_type = 'client backend' GROUP BY usename, datname, state ORDER BY 1" | sed 's/^/  /'
echo "idle in transaction: $(sql "SELECT count(*) FROM pg_stat_activity WHERE state LIKE 'idle in transaction%'")  oldest open transaction: $(sql "SELECT coalesce(max(now() - xact_start)::text, '(none)') FROM pg_stat_activity WHERE xact_start IS NOT NULL AND pid <> pg_backend_pid()")"
echo "prepared transactions: $(sql 'SELECT count(*) FROM pg_prepared_xacts')"
echo "-- alembic (read-only, inside the existing worker container)"
docker exec -i asistenteia-worker-1 python - < "$HERE/readonly_alembic_check.py" 2>&1 | grep -v "^INFO\|^$" | cut -c1-160
