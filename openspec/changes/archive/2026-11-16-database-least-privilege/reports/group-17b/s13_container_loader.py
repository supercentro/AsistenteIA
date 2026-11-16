"""Runs INSIDE a throw-away container of a new image (TD-030, S13): load one service's settings from an environment received on stdin.

    <env JSON on stdin> | docker run -i --rm --network none --entrypoint python <image> -c "$(cat s13_container_loader.py)" <mode>

modes: api-asis worker-asis (the real file as it is today), api worker migrator cli roles verify (the simulated post-transformation
environment). Prints one verdict line with variable NAMES only (never a value, never a URL). Exit 0 on success, 1 on failure.
"""

import json
import os
import re
import sys
from collections.abc import Callable

env = json.load(sys.stdin)
os.environ.update(env)
legacy = [n for n in os.environ if re.match(r"^(POSTGRES_(USER|PASSWORD|DB)|TEST_[A-Z0-9_]+)$", n)]
from app.core import config as c  # the environment must be in place first

which = sys.argv[1]
loaders: dict[str, Callable[[], object]] = {
    "api": lambda: c.load_settings(None),
    "api-asis": lambda: c.load_settings(None),
    "worker": lambda: c.load_worker_settings(None),
    "worker-asis": lambda: c.load_worker_settings(None),
    "migrator": lambda: c.load_migration_settings(None),
    "cli": lambda: c.load_cli_settings(None),
    "roles": lambda: c.load_roles_settings(None),
    "verify": lambda: c.load_verify_settings(None),
}
try:
    loaders[which]()
    print(f"OK   {which:<12} settings load; {len(env)} variables received; legacy administrator/test variables present: {len(legacy)}")
except Exception as exc:  # noqa: BLE001 - report the names of the offending variables, whatever the failure
    names = sorted(set(re.findall(r"\b([A-Z][A-Z0-9_]{2,}):", str(exc))))
    print(f"FAIL {which:<12} {type(exc).__name__}; variables named: {names or 'none'}")
    sys.exit(1)
