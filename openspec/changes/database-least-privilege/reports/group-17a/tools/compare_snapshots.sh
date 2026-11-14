#!/usr/bin/env bash
# Compare two snapshots made with snapshot_db.sql / snapshot_cluster.sql (group 17A tool).
#   bash compare_snapshots.sh <before> <after> [ignore_regex]
# Identity lines (`server`, `system_identifier`, `sessions*`, `postmaster_start`, `database_oid`) are always
# ignored; the optional regex removes further lines (for example the rows written by the services).
# With NORMALIZE=1 an ACL that PostgreSQL writes explicitly after a GRANT or a REASSIGN, and that means the
# same as the default (NULL) one, is read as `(default)`: owner-only table ACL, owner plus PUBLIC on a
# database, templates with PUBLIC connect (sorted). Ownership, roles and every other line stay strict.
A="${1:?before}"; B="${2:?after}"; EXTRA="${3:-^$}"
norm() { if [ "${NORMALIZE:-0}" = 1 ]; then
  sed -E 's/acl=\{asistente=arwdDxt\/asistente\}/acl=(default)/; s/\{asistente=CTc\/asistente,=Tc\/asistente\}|\{=Tc\/asistente,asistente=CTc\/asistente\}/(default)/; s/\{asistente=CTc\/asistente,=c\/asistente\}/{=c\/asistente,asistente=CTc\/asistente}/'
  else cat; fi; }
f() { grep -vE '^(server|system_identifier|sessions[a-z_]*|sessions_on_this_database|postmaster_start|database_oid)\|' "$1" | grep -vE "$EXTRA" | norm; }
# A comparison of two empty or error-only files must never print IDENTICAL: both sides need MIN_LINES lines
# (default 50; a database snapshot has about 120, a cluster snapshot about 12: pass MIN_LINES=5 for those).
NA=$(f "$A" | wc -l); NB=$(f "$B" | wc -l)
if [ "$NA" -lt "${MIN_LINES:-50}" ] || [ "$NB" -lt "${MIN_LINES:-50}" ]; then
  echo "TOO FEW LINES ($NA and $NB, minimum ${MIN_LINES:-50}): one of the snapshots is empty or an error" >&2; exit 2
fi
if grep -qE '^(psql:|ERROR:)' "$A" "$B"; then echo "A SNAPSHOT CONTAINS A PSQL ERROR" >&2; exit 2; fi
diff <(f "$A") <(f "$B") && echo "IDENTICAL ($NA lines compared)"
