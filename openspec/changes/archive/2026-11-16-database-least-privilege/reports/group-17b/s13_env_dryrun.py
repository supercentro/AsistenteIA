"""READ-ONLY dry run of the env-file transformation of step 17B.2 (TD-030, S13). Prints NAMES and verdicts, never a value.

    python s13_env_dryrun.py report <backend folder>          # names, legacy names, identities, required names per service
    python s13_env_dryrun.py compare <backend folder>          # stdin: docker compose config --format json; names and booleans only
    python s13_env_dryrun.py env    <backend folder> <service> # JSON of the SIMULATED environment of a service, for a pipe into a
                                                              # throw-away container (api|worker|migrator|cli|roles|verify|api-asis|worker-asis)

Nothing is written. `env` emits the simulated post-transformation environment on stdout so that it can be piped (never put on a
command line, never saved) into `docker run -i --network none`: the real file values stay in memory, the new role passwords are
random values that exist only in that pipe, and DATABASE_URL gets the planned restricted role instead of the administrator.
"""

from __future__ import annotations

import json
import re
import secrets
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

LEGACY = re.compile(r"^(POSTGRES_(USER|PASSWORD|DB)|TEST_[A-Z0-9_]+)$")
ROLES = {"migrator": "asistente_migrator", "app": "asistente_app", "worker": "asistente_worker", "cli": "asistente_cli"}
REQUIRED = {  # variables without a default in app/core/config.py (read from the code, not from the files)
    "api": ["DATABASE_URL", "JWT_SECRET"],
    "worker": ["DATABASE_URL"],
    "migrator": ["MIGRATION_DATABASE_URL"],
    "cli": ["CLI_DATABASE_URL"],
    "roles": ["ADMIN_DATABASE_URL", "DB_MIGRATOR_PASSWORD", "DB_APP_PASSWORD", "DB_WORKER_PASSWORD", "DB_CLI_PASSWORD"],
}
LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")


def read_pairs(path: Path) -> dict[str, str]:
    pairs: dict[str, str] = {}
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for raw in handle:
            match = LINE.match(raw.rstrip("\r\n"))
            if match:
                value = match.group(2).split(" #")[0].strip()
                pairs[match.group(1)] = value
    return pairs


def url_parts(value: str) -> tuple[str, str, str, str]:
    parts = urlsplit(value)
    return unquote(parts.username or ""), unquote(parts.password or ""), parts.hostname or "", parts.path.lstrip("/")


def build_url(user: str, password: str, database: str) -> str:
    return f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}@db:5432/{database}"


def load(folder: Path) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    for name in (".env", ".env.worker", ".env.db"):
        if not (folder / name).is_file():
            print(f"missing file: {name}")
            sys.exit(2)
    return read_pairs(folder / ".env"), read_pairs(folder / ".env.worker"), read_pairs(folder / ".env.db")


def report(folder: Path) -> int:
    api, worker, admin = load(folder)
    ok = True
    admin_user, admin_pw = admin.get("POSTGRES_USER", ""), admin.get("POSTGRES_PASSWORD", "")
    print(f"files read: .env ({len(api)} names), .env.worker ({len(worker)} names), .env.db ({len(admin)} names)")
    print(f".env.db holds: {sorted(admin)}")
    for label, pairs in ((".env", api), (".env.worker", worker)):
        legacy = sorted(n for n in pairs if LEGACY.match(n))
        print(f"{label}: legacy names that --strip-legacy removes or moves: {legacy or 'none'}")
        db_url = pairs.get("DATABASE_URL")
        if db_url is None:
            print(f"{label}: DATABASE_URL MISSING")
            ok = False
            continue
        user, pw, host, database = url_parts(db_url)
        is_admin = user == admin_user and pw == admin_pw
        print(f"{label}: DATABASE_URL is the administrator of .env.db: {is_admin} (the tool requires True); host={host}; database={database}")
        ok = ok and is_admin
        after = sorted(n for n in pairs if not LEGACY.match(n))
        print(f"{label}: after the transformation no POSTGRES_* or TEST_* name remains: {not any(LEGACY.match(n) for n in after)}")
    present_after = {
        "api": {n for n in api if not LEGACY.match(n)},
        "worker": {n for n in worker if not LEGACY.match(n)},
        "migrator": {"MIGRATION_DATABASE_URL"},
        "cli": {"CLI_DATABASE_URL"},
        "roles": {"ADMIN_DATABASE_URL", "DB_MIGRATOR_PASSWORD", "DB_APP_PASSWORD", "DB_WORKER_PASSWORD", "DB_CLI_PASSWORD"},
    }
    for service, names in REQUIRED.items():
        missing = [n for n in names if n not in present_after[service]]
        print(f"service {service}: required names {names}; missing after the transformation: {missing or 'none'}")
        ok = ok and not missing
    users = {"api": ROLES["app"], "worker": ROLES["worker"], "migrator": ROLES["migrator"], "cli": ROLES["cli"], "admin": admin_user}
    print(f"identities per service: api={users['api']}, worker={users['worker']}, migrator={users['migrator']}, cli={users['cli']}; roles file holds the administrator ({'<administrator>'})")
    print(f"the five identities are distinct: {len(set(users.values())) == 5}")
    ok = ok and len(set(users.values())) == 5
    print(f"new files that already exist in the folder: {[n for n in ('.env.roles', '.env.migrate', '.env.cli', '.env.test', '.env.pre-17b') if (folder / n).exists()] or 'none'}")
    print("RESULT", "COMPATIBLE" if ok else "INCOMPATIBLE")
    return 0 if ok else 1


def simulated(folder: Path, service: str) -> dict[str, str]:
    # the "as is" modes read only the one file they stand for (not .env.db)
    for mode, name in (("api-asis", ".env"), ("worker-asis", ".env.worker")):
        if service == mode:
            if not (folder / name).is_file():
                print(f"missing file: {name}", file=sys.stderr)
                sys.exit(2)
            return read_pairs(folder / name)
    api, worker, admin = load(folder)
    admin_user, admin_pw = admin["POSTGRES_USER"], admin["POSTGRES_PASSWORD"]
    database = url_parts(api["DATABASE_URL"])[3] or "asistenteia"

    def fresh() -> str:  # random values that exist only in the pipe
        return secrets.token_urlsafe(24)

    if service == "api-asis":
        return dict(api)  # the file as it is today, to prove the new image reads it unchanged
    if service == "worker-asis":
        return dict(worker)
    if service == "api":
        env = {n: v for n, v in api.items() if not LEGACY.match(n)}
        env["DATABASE_URL"] = build_url(ROLES["app"], fresh(), database)
        return env
    if service == "worker":
        env = {n: v for n, v in worker.items() if not LEGACY.match(n)}
        env["DATABASE_URL"] = build_url(ROLES["worker"], fresh(), database)
        return env
    if service == "migrator":
        return {"MIGRATION_DATABASE_URL": build_url(ROLES["migrator"], fresh(), database)}
    if service == "cli":
        return {"CLI_DATABASE_URL": build_url(ROLES["cli"], fresh(), database)}
    roles = {
        "ADMIN_DATABASE_URL": build_url(admin_user, admin_pw, "postgres"),  # the REAL administrator, in memory only
        "DB_MIGRATOR_PASSWORD": fresh(),
        "DB_APP_PASSWORD": fresh(),
        "DB_WORKER_PASSWORD": fresh(),
        "DB_CLI_PASSWORD": fresh(),
    }
    if service == "roles":
        return roles
    if service == "verify":
        return {"MIGRATION_DATABASE_URL": build_url(ROLES["migrator"], fresh(), database), **roles}
    print("unknown service")
    sys.exit(2)


def compare(folder: Path) -> int:
    """Read `docker compose config --format json` on stdin and check that the environment Compose resolves for backend and worker
    equals the pairs this parser reads from .env and .env.worker. Prints names and booleans only."""
    config = json.load(sys.stdin)
    ok = True
    for service, name in (("backend", ".env"), ("worker", ".env.worker")):
        resolved = config.get("services", {}).get(service, {}).get("environment", {})
        mine = read_pairs(folder / name)
        differing = sorted(k for k, v in mine.items() if resolved.get(k) != v)
        extra = sorted(set(resolved) - set(mine))
        same = not differing and not extra
        ok = ok and same
        print(f"compose {service}: {len(resolved)} names resolved, {len(mine)} in {name}; values equal: {same}; differing: {differing or 'none'}; only in compose: {extra or 'none'}")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "compare":
        return compare(Path(argv[1]))
    if len(argv) >= 2 and argv[0] == "report":
        return report(Path(argv[1]))
    if len(argv) == 3 and argv[0] == "env":
        sys.stdout.write(json.dumps(simulated(Path(argv[1]), argv[2])))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
