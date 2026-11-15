"""Change the password of a PostgreSQL role (step 17B.6, TD-038) without the password ever appearing in a process argument, a log,
a generated script or the shell history. Names and verdicts only.

    python rotate_db_role.py alter  --container <db container> --role <role> --password-file <file>
    python rotate_db_role.py probe  --network <docker network> --host <db host> --role <role> --password-file <file> --expect accept|reject [--database postgres] [--image <image with psql>]
    python rotate_db_role.py check  --container <db container>
  (probe also accepts --from-env-file F --var NAME [--as-url] to read the password from an env variable, or from the userinfo of a URL variable)

How the secret travels:
  * the password is read from a file (one line, letters, digits, '-' and '_', 32 to 128 characters; owner-only, outside the repository);
  * `alter` does NOT send the password to the server: it sends the SCRAM-SHA-256 VERIFIER (salt, StoredKey, ServerKey) computed here, as
    `ALTER ROLE "<role>" PASSWORD 'SCRAM-SHA-256$...'` on STANDARD INPUT of `docker exec -i <container> psql -f -` (no argument carries it;
    the server and its statement log never see the cleartext; psql runs non-interactively, so there is no psql history);
  * `probe` hands the password to a throw-away container on its STANDARD INPUT (it is exported only inside that container, so it is in no
    argument and not in the container configuration) and connects from ANOTHER container over the Docker network: inside the database container the loopback address is trusted by pg_hba, so a check
    from there would prove nothing.
Exit codes: 0 ok, 1 refused or the expectation failed, 2 usage or missing file, 3 the server rejected the statement or the container did not answer (an `alter` may or may not have been applied: probe), 4 a local error (nothing was sent), 130 interrupted (an `alter` may or may not have been applied: probe).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PASSWORD = re.compile(r"[A-Za-z0-9_-]{32,128}")
ROLE = re.compile(r"[a-z_][a-z0-9_]{0,62}")
ITERATIONS = 4096


def say(message: str) -> None:
    print(message, flush=True)


def stop(message: str, code: int) -> SystemExit:
    say(message)
    return SystemExit(code)


def read_password(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024:
        raise stop("REFUSED the password file is missing, a link, or larger than 1 KB", 2)
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1 or not PASSWORD.fullmatch(lines[0]):
        raise stop("REFUSED the password file must hold ONE line of 32 to 128 letters, digits, '-' or '_'", 1)
    return lines[0]


def read_env_secret(path: Path, name: str) -> str:
    """A password from `NAME=value` in an env file (the CURRENT or the OLD password, whose format is not ours to choose)."""
    if path.is_symlink() or not path.is_file():
        raise stop("REFUSED the env file is missing or a link", 2)
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        if raw.startswith(name + "="):
            value = raw[len(name) + 1 :].split(" #")[0].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]  # Compose strips one pair of matching quotes
            if value and len(value) <= 256 and chr(0) not in value:
                return value
    raise stop(f"REFUSED {name} is missing or empty in the env file", 1)


def password_of_url(value: str, role: str) -> str:
    """The password inside `scheme://user:password@host/db` (percent-decoded); the user must be the role being probed."""
    from urllib.parse import unquote, urlsplit

    parts = urlsplit(value.replace("+psycopg://", "://", 1))
    if "://" not in value or unquote(parts.username or "") != role or not parts.password:
        raise stop("REFUSED the variable is not a URL of that role with a password", 1)
    return unquote(parts.password)


def scram_verifier(password: str, salt: bytes | None = None, iterations: int = ITERATIONS) -> str:
    """SCRAM-SHA-256 verifier as PostgreSQL stores it (RFC 5802 / RFC 7677)."""
    salt = salt if salt is not None else os.urandom(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    def b64(raw: bytes) -> str:
        return base64.b64encode(raw).decode("ascii")

    return f"SCRAM-SHA-256${iterations}:{b64(salt)}${b64(stored_key)}:{b64(server_key)}"


def docker(args: list[str], *, stdin: bytes | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    prefix = ["docker"]
    if os.environ.get("ROT_TEST_HOOKS") == "1" and os.environ.get("ROT_DOCKER_CMD"):
        prefix = json.loads(os.environ["ROT_DOCKER_CMD"])  # test hook: a recording wrapper around the real docker client
    return subprocess.run([*prefix, *args], input=stdin, capture_output=True, env={**os.environ, **(env or {})}, check=False)


def cmd_check(container: str) -> int:
    proc = docker(["exec", "-i", container, "sh", "-c", 'psql -U "$POSTGRES_USER" -d postgres -At -c "show log_statement" -c "show password_encryption"'])
    if proc.returncode != 0:
        say("CHECK FAILED the container does not answer")
        return 3
    log_statement, encryption = (proc.stdout.decode().split() + ["?", "?"])[:2]
    say(f"CHECK log_statement={log_statement}; password_encryption={encryption} (the verifier is sent, so the cleartext is never logged either way)")
    return 0 if encryption == "scram-sha-256" else 1


def cmd_alter(container: str, role: str, password: str, require_superuser: bool = False) -> int:
    if not ROLE.fullmatch(role):
        say("REFUSED the role name must be lower case letters, digits and '_'")
        return 1
    verifier = scram_verifier(password)
    guard = ""
    if require_superuser:  # 17B.6: the role being altered MUST be a superuser, so a mistyped --role can never change a restricted role
        guard = f"DO $guard$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}' AND rolsuper) THEN RAISE EXCEPTION 'not a superuser'; END IF; END $guard$;\n"  # noqa: S608 - `role` already matched ROLE (lower case letters, digits, underscore): it cannot carry SQL
    sql = f'{guard}ALTER ROLE "{role}" PASSWORD \'{verifier}\';\n'.encode()
    proc = docker(["exec", "-i", container, "sh", "-c", 'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -q -f -'], stdin=sql)
    if proc.returncode != 0:
        say(f"ALTER ROLE FAILED for {role}: the server rejected the statement (exit {proc.returncode}); nothing is known to have changed")
        return 3
    say(f"ALTER ROLE OK {role}: SCRAM-SHA-256 verifier installed ({ITERATIONS} iterations); the cleartext never reached the server")
    return 0


def cmd_probe(network: str, host: str, role: str, password: str, expect: str, database: str, image: str) -> int:
    if not ROLE.fullmatch(role) or not re.fullmatch(r"[A-Za-z0-9_.-]+", host) or not re.fullmatch(r"[A-Za-z0-9_]+", database):
        say("REFUSED malformed role, host or database")
        return 1
    # The password travels on STANDARD INPUT of the throw-away container and is exported inside it only: it is in no argument and not
    # in the container configuration (`docker inspect`), unlike `-e PGPASSWORD=...`. Host, role and database are validated above.
    inner = f"IFS= read -r PGPASSWORD; export PGPASSWORD PGCONNECT_TIMEOUT=8; exec psql -h {host} -U {role} -d {database} -Atc 'select 1'"
    proc = docker(["run", "-i", "--rm", "--network", network, "--entrypoint", "sh", image, "-c", inner], stdin=(password + "\n").encode())
    accepted = proc.returncode == 0 and proc.stdout.decode().strip() == "1"
    rejected = proc.returncode != 0 and b"password authentication failed" in proc.stderr
    if expect == "accept":
        say("PROBE OK the password is ACCEPTED over the Docker network" if accepted else "PROBE FAIL the password was NOT accepted")
        return 0 if accepted else 1
    say("PROBE OK the password is REJECTED over the Docker network" if rejected else "PROBE FAIL the password was not rejected with an authentication failure")
    return 0 if rejected else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["alter", "probe", "check"])
    parser.add_argument("--container")
    parser.add_argument("--role")
    parser.add_argument("--password-file")
    parser.add_argument("--from-env-file", help="read the password from NAME=value in this env file instead (the current or the old password)")
    parser.add_argument("--var", default="POSTGRES_PASSWORD")
    parser.add_argument("--require-superuser", action="store_true", help="alter only: refuse (nothing changed) unless the role is a superuser; mandatory in the 17B.6 procedure")
    parser.add_argument("--as-url", action="store_true", help="the variable is a URL: take the password of its userinfo (the user must be --role); proves the stored URL form works")
    parser.add_argument("--network")
    parser.add_argument("--host")
    parser.add_argument("--expect", choices=["accept", "reject"])
    parser.add_argument("--database", default="postgres")
    parser.add_argument("--image", default="pgvector/pgvector:0.8.7-pg15")
    a = parser.parse_args(argv)
    password = ""
    if a.command in ("alter", "probe"):
        if bool(a.password_file) == bool(a.from_env_file):
            say("give exactly one of --password-file and --from-env-file")
            return 2
        try:
            password = read_password(Path(a.password_file)) if a.password_file else read_env_secret(Path(a.from_env_file), a.var)
            if a.as_url:
                password = password_of_url(password, a.role or "")
        except SystemExit:
            raise
        except Exception as exc:  # urlsplit and decode errors can echo the value: type only
            say(f"FAILED unexpected {type(exc).__name__}; no detail is shown")
            return 4
    try:
        if a.command == "check" and a.container:
            return cmd_check(a.container)
        if a.command == "alter" and a.container and a.role:
            return cmd_alter(a.container, a.role, password, a.require_superuser)
        if a.command == "probe" and a.network and a.host and a.role and a.expect:
            return cmd_probe(a.network, a.host, a.role, password, a.expect, a.database, a.image)
    except KeyboardInterrupt:
        say("INTERRUPTED: the state of the database is unknown for an alter; run the read-only probes before anything else")
        return 130
    except Exception as exc:  # no traceback: an error message must never carry the password that is in memory
        say(f"FAILED unexpected {type(exc).__name__}; no detail is shown")
        return 4
    say("missing argument for this command")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
