"""List the containers (running or stopped) whose configuration still carries a role password (SEC-17B-01, step 0b of the rotation).

    python check_containers_for_value.py <backend folder> [--var DB_MIGRATOR_PASSWORD] [--file .env.roles]

The value is read from the env file in memory, compared with the output of `docker inspect` of every container and never printed: only
the number of containers inspected and the short ids and names of those that hold it. Exit 0: none holds it; 1: some do (remove them
by exact name with `docker rm`); 2: usage or unreadable file or Docker. An unexpected error shows its type only (never a traceback).
Test hook: ROT_TEST_HOOKS=1 with ROT_DOCKER_CMD (a JSON list) replaces the docker client, as in rotate_db_role.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote


def docker(args: list[str]) -> subprocess.CompletedProcess[str]:
    prefix = ["docker"]
    if os.environ.get("ROT_TEST_HOOKS") == "1" and os.environ.get("ROT_DOCKER_CMD"):
        prefix = list(json.loads(os.environ["ROT_DOCKER_CMD"]))
    return subprocess.run(  # noqa: S603 - fixed argv built here, no shell, no user text
        [*prefix, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )


def read_value(folder: Path, file_name: str, var: str) -> str:
    path = folder / file_name
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"REFUSED {file_name} is missing or a link")
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", raw)
        if match and match.group(1) == var:
            value = match.group(2).split(" #")[0].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]  # Compose strips one pair of matching quotes
            if len(value) >= 16:
                return value
    raise SystemExit(f"REFUSED {var} is missing or too short in {file_name}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder")
    parser.add_argument("--var", default="DB_MIGRATOR_PASSWORD")
    parser.add_argument("--file", default=".env.roles")
    args = parser.parse_args(argv)
    try:
        value = read_value(Path(args.folder), args.file, args.var)
        escaped = json.dumps(value)[1:-1]
        go_escaped = escaped.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")  # Go's encoder (docker inspect) escapes these three
        forms = {value, quote(value, safe=""), escaped, go_escaped}  # raw, percent-encoded, JSON-escaped (both encoders)
        listing = docker(["ps", "-a", "-q", "--no-trunc"])
        if listing.returncode != 0:
            print("FAILED docker does not answer")
            return 2
        ids = listing.stdout.split()
        holders: list[str] = []
        for container_id in ids:
            inspected = docker(["inspect", container_id])
            if inspected.returncode == 0 and any(form in inspected.stdout for form in forms):
                name = docker(["inspect", "-f", "{{.Name}}", container_id]).stdout.strip().lstrip("/")
                holders.append(f"{container_id[:12]} ({name})")
    except SystemExit as exc:
        print(exc.code)
        return 2
    except Exception as exc:  # noqa: BLE001 - the message of a parser error can echo the value: type only
        print(f"FAILED unexpected {type(exc).__name__}; no detail is shown")
        return 2
    print(f"CONTAINERS inspected: {len(ids)}; holding the value: {len(holders)}")
    for holder in holders:
        print(f"  HOLDS {holder}")
    return 1 if holders else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
