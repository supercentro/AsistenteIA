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
diff <(f "$A") <(f "$B") && echo "IDENTICAL ($(f "$A" | wc -l) lines compared)"
