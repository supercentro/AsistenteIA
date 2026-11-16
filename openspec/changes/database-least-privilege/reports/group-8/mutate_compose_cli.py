"""Mutation checks of the cli service of docker-compose.yml (task 8.7). The repository file is never edited: each
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
    (
        "the API receives the CLI credential file",
        "    env_file:\n      - ./backend/.env\n    ports:",
        "    env_file:\n      - ./backend/.env\n      - ./backend/.env.cli\n    ports:",
    ),
    ("the cli service starts with every plain up", '    profiles: ["cli"]\n', ""),
    (
        "the worker receives the CLI credential file",
        "      - ./backend/.env.worker\n",
        "      - ./backend/.env.worker\n      - ./backend/.env.cli\n",
    ),
    (
        "the cli service restarts after exit",
        '    entrypoint: ["python", "-m", "app.cli"]\n    restart: "no"',
        '    entrypoint: ["python", "-m", "app.cli"]\n    restart: always',
    ),
    (
        "the cli service publishes a port",
        '    entrypoint: ["python", "-m", "app.cli"]\n',
        '    entrypoint: ["python", "-m", "app.cli"]\n    ports:\n      - "127.0.0.1:9998:9998"\n',
    ),
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
