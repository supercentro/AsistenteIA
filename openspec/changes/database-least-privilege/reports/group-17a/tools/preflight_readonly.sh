#!/usr/bin/env bash
# Read-only preflight evidence of a PostgreSQL container (group 17A tool, used in 17B step 1).
#
#   bash preflight_readonly.sh <container> <database> <output directory> [expected_backup_sha256]
#
# Opens only read-only sessions (default_transaction_read_only=on), prints no secret (the administrator
# NAME is read from the container, the password never), and writes: identity.txt, snapshot-db.txt,
# snapshot-cluster.txt, activity.txt and SHA256SUMS. It changes nothing: no container is stopped, no
# volume or file of the application is touched.
set -u
export MSYS_NO_PATHCONV=1
C="${1:?container}"; DB="${2:?database}"; OUT="${3:?output directory}"; EXPECTED="${4:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT"
q() { docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' "$C" sh -c 'psql -U "$POSTGRES_USER" -d "'"$1"'" -At -F "|" -v ON_ERROR_STOP=1' ; }
{
  echo "time_utc|$(date -u +%FT%TZ)"
  echo "container|$C"
  docker inspect "$C" --format 'container_id|{{.Id}}
image|{{.Config.Image}}
image_id|{{.Image}}
created|{{.Created}}
state|{{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}
networks|{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}
mounts_json|{{json .Mounts}}
published_ports|{{range $p,$b := .NetworkSettings.Ports}}{{$p}}={{range $b}}{{.HostIp}}:{{.HostPort}} {{end}}{{end}}
compose_project|{{index .Config.Labels "com.docker.compose.project"}}'
  echo "SELECT 'connected_database', current_database();
        SELECT 'connected_user', current_user;
        SELECT 'server_port', current_setting('port');
        SELECT 'postmaster_start', pg_postmaster_start_time();
        SELECT 'system_identifier', system_identifier FROM pg_control_system();
        SELECT 'server', version();
        SELECT 'read_only_session', current_setting('transaction_read_only');" | q "$DB"
  echo "databases|$(echo "SELECT string_agg(datname, ',' ORDER BY datname) FROM pg_database" | q postgres)"
  echo "free_disk_gb_where_the_output_goes|$(df -BG --output=avail "$OUT" 2>/dev/null | tail -1 | tr -d ' G')"
  echo "free_ram_gb|$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" 2>/dev/null | tr -d '\r')"
} > "$OUT/identity.txt" 2>&1
q "$DB" < "$HERE/snapshot_db.sql" > "$OUT/snapshot-db.txt" 2>&1
q postgres < "$HERE/snapshot_cluster.sql" > "$OUT/snapshot-cluster.txt" 2>&1
echo "SELECT 'open_transactions_older_than_1_min', count(*) FROM pg_stat_activity WHERE xact_start < now() - interval '1 minute' AND pid <> pg_backend_pid();
      SELECT 'idle_in_transaction', count(*) FROM pg_stat_activity WHERE state LIKE 'idle in transaction%' AND pid <> pg_backend_pid();
      SELECT 'prepared_transactions', count(*) FROM pg_prepared_xacts;
      SELECT 'ungranted_locks', count(*) FROM pg_locks WHERE NOT granted;
      SELECT 'sessions_by_user', coalesce(usename,'?')||' on '||coalesce(datname,'-')||' x'||count(*) FROM pg_stat_activity WHERE backend_type='client backend' AND pid <> pg_backend_pid() GROUP BY usename, datname ORDER BY 2;
      SELECT 'clients_by_address_and_application', x FROM (SELECT coalesce(client_addr::text,'unix socket')||' / '||coalesce(nullif(application_name,''),'(no name)')||' x'||count(*) AS x FROM pg_stat_activity WHERE backend_type='client backend' AND pid <> pg_backend_pid() GROUP BY client_addr, application_name) s ORDER BY x;
      SELECT 'login_roles_other_than_the_administrator', coalesce(string_agg(rolname, ',' ORDER BY rolname), '(none)') FROM pg_roles WHERE rolcanlogin AND rolname !~ '^pg_' AND rolsuper = false;
      SELECT 'long_running_queries_over_30s', count(*) FROM pg_stat_activity WHERE state = 'active' AND query_start < now() - interval '30 seconds' AND pid <> pg_backend_pid();" | q postgres > "$OUT/activity.txt" 2>&1
( cd "$OUT" && sha256sum identity.txt snapshot-db.txt snapshot-cluster.txt activity.txt > SHA256SUMS )
if grep -qE '^(psql:|ERROR:)' "$OUT"/*.txt; then echo "PREFLIGHT ERROR: a query failed:"; grep -hE '^(psql:|ERROR:)' "$OUT"/*.txt | head -3; exit 1; fi
grep -q '^login_roles_other_than_the_administrator|' "$OUT/activity.txt" || { echo "PREFLIGHT ERROR: activity.txt is incomplete"; exit 1; }
echo "written to $OUT: $(ls "$OUT" | tr '\n' ' ')"
grep -hE "^(connected|read_only|open_transactions|idle_in|prepared|ungranted|long_running|revision|free_disk|clients_by|login_roles)" "$OUT/identity.txt" "$OUT/activity.txt" "$OUT/snapshot-db.txt" | sed 's/^/  /'
[ -z "$EXPECTED" ] || echo "expected backup sha256 given: $EXPECTED"
