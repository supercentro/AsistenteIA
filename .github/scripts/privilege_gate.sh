#!/usr/bin/env bash
# The mandatory PostgreSQL privilege gate (change `database-least-privilege`, decision D5, task 10.1).
#
# usage: privilege_gate.sh <step>
#   prerequisites    every variable the gate needs is present; ephemeral credentials are generated
#   clusters         both clusters are the exclusive, empty, local pgvector clusters of this job
#   flow             the real commands: db-bootstrap, db-migrate (0006 + grants), db-verify, alembic check
#   drift-selfcheck  a deliberate drift must make db-verify fail, and db-grants must heal it
#   privilege-unit   the matrix, inventory and workflow unit tests
#   role-suites      the role-bound integration suites (marker role_bound), the `tests` cluster
#   roles-mode       the existing API and ingestion tests under the production roles (--least-privilege)
#   summary          every report is clean, complete and not skipped; prints the number of tests
#
# Every step runs with `set -euo pipefail`: a failing command fails the step and the job. Nothing
# here ignores an exit code. The administrator credentials of each cluster reach only the commands
# that create roles and the tests that build clusters; the API and worker processes of the role-bound
# tests get their own role URLs from the tests themselves. Secrets generated here are masked and
# written to a private file in the runner temp directory, never to an artifact.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$HERE/../../backend"
cd "$BACKEND"

RUNNER_TEMP_DIR="${RUNNER_TEMP:-/tmp}"
REPORTS="${GATE_REPORTS:-$RUNNER_TEMP_DIR/privilege-reports}"
SECRETS_FILE="${GATE_SECRETS:-$RUNNER_TEMP_DIR/privilege-gate-secrets.env}"
PYRUN="${PYRUN:-uv run --frozen python}"
FLOW_HOST="${FLOW_HOST:-${GATE_HOST:-127.0.0.1}}"
TESTS_HOST="${TESTS_HOST:-${GATE_HOST:-127.0.0.1}}"
APP_DATABASE="asistenteia_ci"

fail() { echo "::error::$*"; exit 1; }

require() {
  local name
  for name in "$@"; do
    [ -n "${!name:-}" ] || fail "missing prerequisite $name"
  done
}

admin_url() { # $1 = host, $2 = port, $3 = database
  echo "postgresql+psycopg://${PG_ADMIN_USER}:${PG_ADMIN_PASSWORD}@${1}:${2}/${3}"
}

role_url() { # $1 = role, $2 = password, $3 = host, $4 = port, $5 = database
  echo "postgresql+psycopg://${1}:${2}@${3}:${4}/${5}"
}

load_secrets() {
  [ -f "$SECRETS_FILE" ] || fail "missing prerequisite: the ephemeral credentials (step prerequisites)"
  # shellcheck disable=SC1090
  source "$SECRETS_FILE"
}

step_prerequisites() {
  require PG_ADMIN_USER PG_ADMIN_PASSWORD FLOW_PORT TESTS_PORT APP_ENV
  [ "$APP_ENV" = "test" ] || fail "APP_ENV must be test"
  [ "$FLOW_PORT" != "$TESTS_PORT" ] || [ "$FLOW_HOST" != "$TESTS_HOST" ] \
    || fail "the two clusters need different ports"
  mkdir -p "$REPORTS"
  umask 077
  local name value
  : > "$SECRETS_FILE"
  while read -r name value; do
    echo "::add-mask::$value"
    printf '%s=%s\n' "$name" "$value" >> "$SECRETS_FILE"
  done < <($PYRUN - <<'PY'
import secrets
for name in ("DB_MIGRATOR_PASSWORD", "DB_APP_PASSWORD", "DB_WORKER_PASSWORD", "DB_CLI_PASSWORD"):
    print(name, secrets.token_urlsafe(24))
PY
  )
  [ "$(wc -l < "$SECRETS_FILE")" -eq 4 ] || fail "the ephemeral credentials were not generated"
  echo "prerequisites present; four ephemeral role credentials generated and masked"
}

step_clusters() {
  require PG_ADMIN_USER PG_ADMIN_PASSWORD FLOW_PORT TESTS_PORT
  export CI_ALLOWED_HOSTS="${CI_ALLOWED_HOSTS:-127.0.0.1,localhost}"
  local flow tests
  flow="$(admin_url "$FLOW_HOST" "$FLOW_PORT" postgres)"
  tests="$(admin_url "$TESTS_HOST" "$TESTS_PORT" postgres)"
  FLOW_ADMIN_URL="$flow" $PYRUN "$HERE/assert_disposable_cluster.py" check flow FLOW_ADMIN_URL
  TESTS_ADMIN_URL="$tests" $PYRUN "$HERE/assert_disposable_cluster.py" check tests TESTS_ADMIN_URL
  FLOW_ADMIN_URL="$flow" TESTS_ADMIN_URL="$tests" \
    $PYRUN "$HERE/assert_disposable_cluster.py" distinct FLOW_ADMIN_URL TESTS_ADMIN_URL
}

roles_environment() { # the four role passwords, for the commands that need them
  echo "DB_MIGRATOR_PASSWORD=$DB_MIGRATOR_PASSWORD DB_APP_PASSWORD=$DB_APP_PASSWORD DB_WORKER_PASSWORD=$DB_WORKER_PASSWORD DB_CLI_PASSWORD=$DB_CLI_PASSWORD"
}

migrator_url() {
  role_url asistente_migrator "$DB_MIGRATOR_PASSWORD" "$FLOW_HOST" "$FLOW_PORT" "$APP_DATABASE"
}

bootstrap() {
  # shellcheck disable=SC2046
  env ADMIN_DATABASE_URL="$(admin_url "$FLOW_HOST" "$FLOW_PORT" postgres)" $(roles_environment) \
    $PYRUN -m app.cli db-bootstrap --database "$APP_DATABASE"
}

migrate() {
  env MIGRATION_DATABASE_URL="$(migrator_url)" $PYRUN -m app.cli db-migrate
}

verify() {
  # shellcheck disable=SC2046
  env MIGRATION_DATABASE_URL="$(migrator_url)" $(roles_environment) $PYRUN -m app.cli db-verify
}

step_flow() {
  require PG_ADMIN_USER PG_ADMIN_PASSWORD FLOW_PORT
  load_secrets
  bootstrap
  migrate
  verify
  env MIGRATION_DATABASE_URL="$(migrator_url)" $PYRUN "$HERE/alembic_check.py"
  echo "second pass: bootstrap, migrate and verify are idempotent"
  bootstrap
  migrate
  verify
}

step_drift_selfcheck() {
  require PG_ADMIN_USER PG_ADMIN_PASSWORD FLOW_PORT
  load_secrets
  # Give the application role a privilege the matrix does not have: db-verify must detect it.
  ADMIN_TO_APP_DATABASE="$(admin_url "$FLOW_HOST" "$FLOW_PORT" "$APP_DATABASE")" $PYRUN - <<'PY'
import os
import psycopg

url = os.environ["ADMIN_TO_APP_DATABASE"].replace("postgresql+psycopg", "postgresql")
with psycopg.connect(url, autocommit=True) as conn:
    conn.execute('GRANT UPDATE ("role") ON TABLE "public"."users" TO "asistente_app"')
PY
  if verify; then
    fail "db-verify did not detect a privilege outside the matrix: the gate cannot see drift"
  fi
  echo "drift detected as expected; healing it with db-grants"
  env MIGRATION_DATABASE_URL="$(migrator_url)" $PYRUN -m app.cli db-grants
  verify
}

step_privilege_unit() {
  mkdir -p "$REPORTS"
  $PYRUN -m pytest -p no:cacheprovider -rs --junitxml="$REPORTS/unit.xml" \
    tests/unit/test_db_privileges_matrix.py tests/unit/test_db_privileges_inventory.py \
    tests/unit/test_db_admin_sql.py tests/unit/test_fetched_value_columns.py \
    tests/unit/test_ci_workflow.py tests/unit/test_ci_gate_scripts.py
}

tests_environment() { # the `tests` cluster, for the pytest steps
  # The flag that allows destructive cluster-wide operations exists only here, only after the
  # cluster proved again that it is the exclusive, empty, local one this job created.
  export CI_ALLOWED_HOSTS="${CI_ALLOWED_HOSTS:-127.0.0.1,localhost}"
  local tests
  tests="$(admin_url "$TESTS_HOST" "$TESTS_PORT" postgres)"
  TESTS_ADMIN_URL="$tests" $PYRUN "$HERE/assert_disposable_cluster.py" check tests TESTS_ADMIN_URL
  export DATABASE_URL
  DATABASE_URL="$(role_url asistente_unused unused "$TESTS_HOST" "$TESTS_PORT" asistenteia)"
  export TEST_DATABASE_URL
  TEST_DATABASE_URL="$(admin_url "$TESTS_HOST" "$TESTS_PORT" tstdb_ci_test)"
  export TEST_ADMIN_DATABASE_URL="$tests"
  export TEST_CLUSTER_IS_DISPOSABLE=true
}

step_role_suites() {
  require PG_ADMIN_USER PG_ADMIN_PASSWORD TESTS_PORT
  mkdir -p "$REPORTS"
  tests_environment
  $PYRUN -m pytest tests/integration -m role_bound -p no:cacheprovider -rs \
    --junitxml="$REPORTS/role-suites.xml"
}

step_roles_mode() {
  require PG_ADMIN_USER PG_ADMIN_PASSWORD TESTS_PORT
  mkdir -p "$REPORTS"
  tests_environment
  # The mode builds the guarded test database itself; it must exist (the suites above drop it).
  $PYRUN - <<'PY'
import os
import psycopg

admin = os.environ["TEST_ADMIN_DATABASE_URL"].replace("postgresql+psycopg", "postgresql")
with psycopg.connect(admin, autocommit=True) as conn:
    if conn.execute("SELECT 1 FROM pg_database WHERE datname = 'tstdb_ci_test'").fetchone() is None:
        conn.execute('CREATE DATABASE "tstdb_ci_test"')
PY
  $PYRUN -m pytest tests/integration --least-privilege -m least_privilege -p no:cacheprovider -rs \
    --junitxml="$REPORTS/roles-mode.xml"
}

step_summary() {
  $PYRUN "$HERE/check_results.py" \
    "privilege unit tests=$REPORTS/unit.xml:${MIN_UNIT:-60}" \
    "role-bound suites=$REPORTS/role-suites.xml:${MIN_ROLE_SUITES:-400}" \
    "roles mode=$REPORTS/roles-mode.xml:${MIN_ROLES_MODE:-480}"
}

case "${1:-}" in
  prerequisites) step_prerequisites ;;
  clusters) step_clusters ;;
  flow) step_flow ;;
  drift-selfcheck) step_drift_selfcheck ;;
  privilege-unit) step_privilege_unit ;;
  role-suites) step_role_suites ;;
  roles-mode) step_roles_mode ;;
  summary) step_summary ;;
  *) fail "unknown step '${1:-}' (see the header of this file)" ;;
esac
