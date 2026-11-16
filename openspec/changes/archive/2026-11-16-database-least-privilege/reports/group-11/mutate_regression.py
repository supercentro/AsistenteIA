"""Mutations that show the updated existing tests are still at least as strong (task 11.1).

usage: python mutate_regression.py <repository root> <scratch directory>

Each mutation edits one file of a COPY of the repository layout and runs the unit tests that read the
environment files, the guard, `alembic/env.py`, the Compose file and the settings. A mutation is
caught when they fail. Integration-level controls (a direct online Alembic run, the CLI process)
are proved by the integration runs of this folder.
"""

import shutil
import subprocess
import sys
from pathlib import Path

TESTS = [
    "tests/unit/test_environment_files.py",
    "tests/unit/test_deployment_files.py",
    "tests/unit/test_compose_database_flow.py",
    "tests/unit/test_test_database_environment.py",
    "tests/unit/test_migration_settings.py",
    "tests/unit/test_db_guard_no_connections.py",
    "tests/unit/test_db_safety.py",
    "tests/unit/test_config.py",
]

# (label, file relative to the repository root, old text, new text)
MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "TEST_DATABASE_URL comes back into the API example (it moved to .env.test.example)",
        "backend/.env.example",
        "# Integration tests: TEST_DATABASE_URL",
        "TEST_DATABASE_URL=postgresql+psycopg://asistente:CHANGE_ME@127.0.0.1:5442/asistenteia_test\n# Integration tests: TEST_DATABASE_URL",
    ),
    (
        "the test example holds a real-looking password",
        "backend/.env.test.example",
        "TEST_DATABASE_URL=postgresql+psycopg://asistente:CHANGE_ME@",
        "TEST_DATABASE_URL=postgresql+psycopg://asistente:s3cret-Real-Pass-123@",
    ),
    (
        "the CLI example holds a real-looking password",
        "backend/.env.cli.example",
        "asistente_cli:CHANGE_ME@",
        "asistente_cli:s3cret-Real-Pass-123@",
    ),
    (
        "the administrator URL example holds a real-looking password",
        "backend/.env.roles.example",
        "ADMIN_DATABASE_URL=postgresql+psycopg://asistente:CHANGE_ME@",
        "ADMIN_DATABASE_URL=postgresql+psycopg://asistente:s3cret-Real-Pass-123@",
    ),
    (
        "the compose file loses the bootstrap service dependency of migrate",
        "docker-compose.yml",
        "      bootstrap:\n        condition: service_completed_successfully\n",
        "      db:\n        condition: service_healthy\n",
    ),
    (
        "the API receives the migrator file",
        "docker-compose.yml",
        "    env_file:\n      - ./backend/.env\n    ports:",
        "    env_file:\n      - ./backend/.env\n      - ./backend/.env.migrate\n    ports:",
    ),
    (
        "the guard compares with nothing when DATABASE_URL is missing",
        "backend/tests/db_support.py",
        '    url = os.environ.get("DATABASE_URL")\n    if not url:\n',
        '    url = os.environ.get("DATABASE_URL")\n    if False:\n',
    ),
    (
        "the administrator URL may name another server",
        "backend/tests/db_support.py",
        "    if (admin.host, admin.port) != (test.host, test.port):\n",
        "    if False:\n",
    ),
    (
        "the migration settings fall back to the API database URL",
        "backend/app/core/config.py",
        "    migration_database_url: SecretStr\n\n    @field_validator",
        '    migration_database_url: SecretStr = Field(validation_alias="DATABASE_URL")\n\n    @field_validator',
    ),
    (
        "the guard accepts a test database named like the application one",
        "backend/app/core/db_safety.py",
        "        if app.database == test.database:\n",
        "        if False:\n",
    ),
]


def main() -> int:
    repo, scratch = Path(sys.argv[1]), Path(sys.argv[2])
    python = str(repo / "backend/.venv/Scripts/python.exe")
    caught = 0
    baseline = scratch / "baseline"
    if baseline.exists():
        shutil.rmtree(baseline)
    baseline.mkdir(parents=True)
    ignore_all = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".env", ".env.db", ".env.worker")
    shutil.copytree(repo / "backend", baseline / "backend", ignore=ignore_all)
    for name in ("docker-compose.yml", ".gitignore"):
        shutil.copy(repo / name, baseline / name)
    for folder in (".github", "docs"):
        shutil.copytree(repo / folder, baseline / folder)
    first = subprocess.run(  # noqa: S603 - fixed arguments, test-only
        [python, "-m", "pytest", *TESTS, "-q", "-p", "no:cacheprovider"],
        cwd=baseline / "backend", capture_output=True, text=True, check=False,
    )
    print(f"unmutated copy: exit {first.returncode} ({first.stdout.strip().splitlines()[-1]})")
    shutil.rmtree(baseline, ignore_errors=True)
    if first.returncode != 0:
        print("the unmutated tests must pass before a mutation means anything")
        return 2
    for index, (label, rel, old, new) in enumerate(MUTATIONS):
        work = scratch / f"m{index}"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        ignore = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".env", ".env.db", ".env.worker")
        shutil.copytree(repo / "backend", work / "backend", ignore=ignore)
        for name in ("docker-compose.yml", ".gitignore"):
            if (repo / name).is_file():
                shutil.copy(repo / name, work / name)
        for folder in (".github", "docs"):
            shutil.copytree(repo / folder, work / folder)
        target = work / rel
        text = target.read_text(encoding="utf-8").replace("\r\n", "\n")
        if text.count(old) != 1:
            print(f"SKIPPED   {label} (pattern found {text.count(old)} times)")
            continue
        target.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
        result = subprocess.run(  # noqa: S603 - fixed arguments, test-only
            [python, "-m", "pytest", *TESTS, "-q", "-p", "no:cacheprovider", "-x"],
            cwd=work / "backend", capture_output=True, text=True, check=False,
        )
        failed = [line for line in result.stdout.splitlines() if line.startswith(("FAILED", "ERROR "))]
        test = failed[0].split("::")[-1].split(" - ")[0] if failed else ""
        status = "CAUGHT   " if result.returncode in {1, 2} and test else "SURVIVED "
        caught += status.startswith("CAUGHT")
        print(f"{status} {label} | {test}")
        shutil.rmtree(work, ignore_errors=True)
    print(f"mutations: {len(MUTATIONS)}, caught: {caught}")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
