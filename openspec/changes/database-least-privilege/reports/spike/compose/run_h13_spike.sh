#!/bin/sh
# H13 on a scratch Compose project (g26cold / g26cold2): records everything to ../out/h13_compose.txt
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/../out/h13_compose.txt"
cd "$HERE" || exit 1
: > "$OUT"
log() { echo "$@" | tee -a "$OUT"; }
gen() { python -c "import secrets;print(secrets.token_hex(10))"; }
mkenv() {
  PWA=$(gen); PWM=$(gen); PWP=$(gen); PWW=$(gen); JWT=$(python -c "import secrets;print(secrets.token_urlsafe(40))")
  printf 'POSTGRES_USER=spk_admin\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=postgres\n' "$PWA" > db.env
  printf 'POSTGRES_PASSWORD=%s\nPW_MIG=%s\nPW_APP=%s\nPW_WORKER=%s\n' "$PWA" "$PWM" "$PWP" "$PWW" > roles.env
  printf 'DATABASE_URL=postgresql+psycopg://cs_migrator:%s@db:5432/cs_db\nAPP_ENV=development\nLOG_LEVEL=WARNING\nJWT_SECRET=%s\n' "$PWM" "$JWT" > migrate.env
  printf 'DB_URL=postgresql://cs_worker:%s@db:5432/cs_db\nMARK=one\n' "$PWW" > worker.env
}
C="docker compose -f compose.yml"
state() { $C ps -a --format '{{.Service}} {{.State}} exit={{.ExitCode}}' | sort | tr '\n' ';'; }
for round in 1 2; do
  mkenv
  log "=== ROUND $round: cold start from nothing (no volume, no containers)"
  $C up -d > /tmp/g26_up.txt 2>&1; rc=$?
  log "up -d rc=$rc"
  sleep 10
  log "state: $(state)"
  log "bootstrap log: $($C logs --no-log-prefix bootstrap 2>&1 | tail -1 | cut -c1-120)"
  log "migrate log:   $($C logs --no-log-prefix migrate 2>&1 | tail -2 | tr '\n' '|' | cut -c1-220)"
  log "worker log:    $($C logs --no-log-prefix worker 2>&1 | tail -1 | cut -c1-160)"
  if [ "$round" = "1" ]; then
    log "=== T2 second 'up -d' on the existing volume"
    S0=$(docker inspect g26cold-bootstrap-1 --format '{{.State.StartedAt}}')
    $C up -d > /tmp/g26_up2.txt 2>&1
    sleep 8
    S1=$(docker inspect g26cold-bootstrap-1 --format '{{.State.StartedAt}}')
    log "bootstrap StartedAt before: $S0"
    log "bootstrap StartedAt after:  $S1  (different = the completed one-shot was started again by a plain 'up -d')"
    log "bootstrap runs in its log: $($C logs --no-log-prefix bootstrap 2>&1 | grep -c 'bootstrap done'); second run verbs: $($C logs --no-log-prefix bootstrap 2>&1 | tail -1 | cut -c1-120)"
    log "worker still running with the same container: $(docker inspect g26cold-worker-1 --format '{{.State.Status}} started={{.State.StartedAt}}')"
    log "=== T3 environment switch"
    sed -i 's/MARK=one/MARK=two/' worker.env
    $C restart worker > /dev/null 2>&1; sleep 5
    log "after 'restart':             $($C logs --no-log-prefix worker 2>&1 | tail -1 | grep -o 'MARK=.*')"
    $C up -d --force-recreate worker > /dev/null 2>&1; sleep 5
    log "after 'up --force-recreate': $($C logs --no-log-prefix worker 2>&1 | tail -1 | grep -o 'MARK=.*')"
    log "=== T4 bootstrap in a profile that is not active while migrate depends on it"
    sed -e 's/^name: g26cold/name: g26cold2/' -e 's#    entrypoint: \["python", "/c/bootstrap.py"\]#    profiles: ["admin"]\n    entrypoint: ["python", "/c/bootstrap.py"]#' compose.yml > compose2.yml
    log "config: $(docker compose -f compose2.yml config -q 2>&1 | head -1 | cut -c1-160)"
    log "up -d (no profile): $(docker compose -f compose2.yml up -d 2>&1 | head -1 | cut -c1-160)"
  fi
  log "=== teardown of the scratch project (round $round)"
  $C down -v > /dev/null 2>&1
  docker compose -f compose2.yml down -v > /dev/null 2>&1
  log "left: containers=$(docker ps -a --filter label=com.docker.compose.project=g26cold -q | wc -l) volumes=$(docker volume ls --format '{{.Name}}' | grep -c g26cold)"
done
rm -f db.env roles.env migrate.env worker.env compose2.yml
