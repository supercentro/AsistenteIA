"""Mutation checks of docker-compose.yml (task 6.1). The repository file is never edited: each
mutation is written to a scratch file, the deployment-file tests are pointed at it through the
COMPOSE_FILE_UNDER_TEST variable, and the run reports whether they failed and which test did.

usage: python mutate_compose.py <repository root> <scratch directory>
"""

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(sys.argv[1])
SCRATCH = pathlib.Path(sys.argv[2])
TESTS = [
    "tests/unit/test_compose_database_flow.py",
    "tests/unit/test_deployment_files.py",
]

MUTATIONS = [
    ("migrate loses its dependency on bootstrap", "      bootstrap:\n        condition: service_completed_successfully\n", "      db:\n        condition: service_healthy\n"),
    ("backend no longer waits for migrate", "      migrate:\n        condition: service_completed_successfully\n    volumes:\n      - ./backend/app:/app/app\n    command:", "    volumes:\n      - ./backend/app:/app/app\n    command:"),
    ("bootstrap restarts after exit", 'command: ["python", "-m", "app.cli", "db-bootstrap", "--database", "asistenteia"]\n    restart: "no"', 'command: ["python", "-m", "app.cli", "db-bootstrap", "--database", "asistenteia"]\n    restart: unless-stopped'),
    ("bootstrap publishes a port", 'command: ["python", "-m", "app.cli", "db-bootstrap", "--database", "asistenteia"]\n', 'command: ["python", "-m", "app.cli", "db-bootstrap", "--database", "asistenteia"]\n    ports:\n      - "127.0.0.1:9999:9999"\n'),
    ("the worker becomes privileged", "    cpus: 4\n", "    privileged: true\n    cpus: 4\n"),
    ("the backend joins the host network", "    ports:\n      - \"127.0.0.1:8000:8000\"\n", "    network_mode: host\n"),
    ("the worker mounts the docker socket", "      - ./backend/app:/app/app:ro\n", "      - ./backend/app:/app/app:ro\n      - /var/run/docker.sock:/var/run/docker.sock\n"),
    ("migrate receives the API file", "      - path: ./backend/.env.migrate\n        required: false\n", "      - ./backend/.env\n"),
    ("bootstrap receives the migrator file", "      - path: ./backend/.env.roles\n        required: false\n", "      - path: ./backend/.env.migrate\n        required: false\n"),
    ("migrate mounts the working tree", 'command: ["python", "-m", "app.cli", "db-migrate"]\n', 'command: ["python", "-m", "app.cli", "db-migrate"]\n    volumes:\n      - ./backend/app:/app/app\n'),
    ("bootstrap moves to an inactive profile", 'command: ["python", "-m", "app.cli", "db-bootstrap", "--database", "asistenteia"]\n', 'command: ["python", "-m", "app.cli", "db-bootstrap", "--database", "asistenteia"]\n    profiles: ["admin"]\n'),
    ("worker loses its dependency on migrate", "      migrate:\n        condition: service_completed_successfully\n    cpus: 4", "    cpus: 4"),
    ("a secret is passed inline to the worker", "    cpus: 4\n", "    environment:\n      JWT_SECRET: inline\n    cpus: 4\n"),
    ("the database port is published on all interfaces", '"127.0.0.1:5442:5432"', '"5442:5432"'),
]

results = []
for label, old, new in MUTATIONS:
    if new is None:
        continue
    compose = SCRATCH / "docker-compose.mutated.yml"
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert text.count(old) >= 1, label
    compose.write_text(text.replace(old, new, 1), encoding="utf-8")
    run = subprocess.run(
        ["uv", "run", "--frozen", "--offline", "pytest", *TESTS, "-q", "-p", "no:cacheprovider", "--no-header", "-x"],
        cwd=ROOT / "backend", capture_output=True, text=True,
        env={**os.environ, "COMPOSE_FILE_UNDER_TEST": str(compose)},
    )
    failed = [line.split("::")[1].split(" ")[0] for line in run.stdout.splitlines() if line.startswith("FAILED")][:1]
    results.append((label, run.returncode, failed))
clean = subprocess.run(
    ["uv", "run", "--frozen", "--offline", "pytest", *TESTS, "-q", "-p", "no:cacheprovider", "--no-header"],
    cwd=ROOT / "backend", capture_output=True, text=True,
)
print(f"unmutated file: exit {clean.returncode} ({clean.stdout.strip().splitlines()[-1]})")
for label, code, failed in results:
    print(("CAUGHT   " if code == 1 else "SURVIVED " if code == 0 else f"INFRA({code}) "), label, "|", failed[0] if failed else "-")
print(f"mutations: {len(results)}, caught: {sum(1 for _, c, _ in results if c == 1)}")
