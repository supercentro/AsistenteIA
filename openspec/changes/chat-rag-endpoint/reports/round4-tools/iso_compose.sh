#!/usr/bin/env bash
# Every Compose command for the isolated project goes through here: fixed project name, fixed
# directory inside the scratch area, and a refusal to run anywhere else.
set -eu
# ISO_SCRATCH: an empty scratch directory outside the repository (its path must contain "scratch").
SP="${ISO_SCRATCH:?set ISO_SCRATCH to the scratch directory}"
DIR="$SP/compose-iso"
case "$DIR" in *scratch*) ;; *) echo "refusing: not in the scratch area" >&2; exit 2;; esac
[ -f "$DIR/docker-compose.verify.yml" ] || { echo "isolated project directory missing" >&2; exit 2; }
cd "$DIR"
exec docker compose -p chatiso --project-directory "$DIR" -f docker-compose.yml -f docker-compose.verify.yml "$@"
