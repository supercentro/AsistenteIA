#!/usr/bin/env bash
# Every Compose command for the isolated project goes through here: fixed project name, fixed
# directory inside the scratch area, and a refusal to run anywhere else.
set -eu
SP="C:/Users/anico/AppData/Local/Temp/claude/8216f42c53299745/37b9475e-8000-414a-a563-2a3020e73979/scratchpad"
DIR="$SP/compose-iso"
case "$DIR" in *scratchpad*) ;; *) echo "refusing: not in the scratch area" >&2; exit 2;; esac
[ -f "$DIR/docker-compose.verify.yml" ] || { echo "isolated project directory missing" >&2; exit 2; }
cd "$DIR"
exec docker compose -p chatiso --project-directory "$DIR" -f docker-compose.yml -f docker-compose.verify.yml "$@"
