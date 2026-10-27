"""The administrative CLI exercised as a real process (`python -m app.cli`), including `main()`."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.database import create_db_engine
from app.models.user import UserRole
from tests.constants import TEST_JWT_SECRET
from tests.integration.helpers import MakeUser

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEACHER_PASSWORD = "process-teacher-password"
STUDENT_PASSWORD = "process-student-password"
SEED_ENV = {
    "SEED_TEACHER_EMAIL": "proc.teacher@example.com",
    "SEED_TEACHER_PASSWORD": TEACHER_PASSWORD,
    "SEED_STUDENT_EMAIL": "proc.student@example.com",
    "SEED_STUDENT_PASSWORD": STUDENT_PASSWORD,
}


def run_cli(
    database_url: str,
    tmp_path: Path,
    args: list[str],
    *,
    extra_env: dict[str, str] | None = None,
    stdin: str = "",
) -> subprocess.CompletedProcess[str]:
    """Run the CLI in an empty working directory so no backend/.env file can leak in."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "HOME", "USERPROFILE"}
    }
    env.update(
        {
            "PYTHONPATH": str(BACKEND_DIR),
            "DATABASE_URL": database_url,
            "JWT_SECRET": TEST_JWT_SECRET,
            "APP_ENV": "test",
        }
    )
    env.update(extra_env or {})
    return subprocess.run(  # noqa: S603 - fixed arguments, test-only
        [sys.executable, "-m", "app.cli", *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        timeout=60,
        check=False,
    )


def accounts(database_url: str) -> dict[str, tuple[str, str]]:
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT email, role::text, password_hash FROM users"))
            return {row[0]: (row[1], row[2]) for row in rows}
    finally:
        engine.dispose()


def all_output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def test_seed_is_rejected_in_production_and_creates_nothing(clean_db: str, tmp_path: Path) -> None:
    result = run_cli(
        clean_db,
        tmp_path,
        ["seed"],
        extra_env={**SEED_ENV, "APP_ENV": "production", "CORS_ORIGINS": "https://app.example"},
    )

    assert result.returncode != 0
    assert "production" in all_output(result)
    assert accounts(clean_db) == {}


def test_seed_without_credentials_fails_naming_the_variables(clean_db: str, tmp_path: Path) -> None:
    result = run_cli(clean_db, tmp_path, ["seed"])

    assert result.returncode != 0
    for name in SEED_ENV:
        assert name in all_output(result)
    assert accounts(clean_db) == {}


def test_seed_with_one_missing_credential_creates_nothing(clean_db: str, tmp_path: Path) -> None:
    partial = {k: v for k, v in SEED_ENV.items() if k != "SEED_STUDENT_PASSWORD"}

    result = run_cli(clean_db, tmp_path, ["seed"], extra_env=partial)

    assert result.returncode != 0
    assert "SEED_STUDENT_PASSWORD" in all_output(result)
    assert accounts(clean_db) == {}


def test_seed_is_idempotent_and_never_prints_passwords(clean_db: str, tmp_path: Path) -> None:
    first = run_cli(clean_db, tmp_path, ["seed"], extra_env=SEED_ENV)
    created = accounts(clean_db)
    second = run_cli(
        clean_db,
        tmp_path,
        ["seed"],
        extra_env={**SEED_ENV, "SEED_TEACHER_PASSWORD": "changed-teacher-password"},
    )

    assert first.returncode == 0
    assert second.returncode == 0
    assert "Created teacher" in first.stdout and "Created student" in first.stdout
    assert "Skipped teacher" in second.stdout and "Skipped student" in second.stdout
    assert accounts(clean_db) == created  # same rows, same hashes
    assert {role for role, _ in created.values()} == {"teacher", "student"}
    for result in (first, second):
        for secret in (TEACHER_PASSWORD, STUDENT_PASSWORD, "changed-teacher-password", "argon2"):
            assert secret not in all_output(result)


def test_create_teacher_with_a_duplicate_email_changes_nothing(
    clean_db: str, tmp_path: Path, make_user: MakeUser
) -> None:
    make_user("taken@example.com", UserRole.STUDENT)
    before = accounts(clean_db)

    result = run_cli(
        clean_db,
        tmp_path,
        ["create-teacher", "--email", "Taken@Example.com", "--password-stdin"],
        stdin=f"{TEACHER_PASSWORD}\n",
    )

    assert result.returncode != 0
    assert "already exists" in all_output(result)
    assert accounts(clean_db) == before  # still a student, hash untouched
    assert TEACHER_PASSWORD not in all_output(result)


def test_create_teacher_creates_the_account_without_echoing_the_password(
    clean_db: str, tmp_path: Path
) -> None:
    result = run_cli(
        clean_db,
        tmp_path,
        ["create-teacher", "--email", "new.teacher@example.com", "--password-stdin"],
        stdin=f"{TEACHER_PASSWORD}\n",
    )

    stored = accounts(clean_db)
    assert result.returncode == 0
    assert stored["new.teacher@example.com"][0] == "teacher"
    assert stored["new.teacher@example.com"][1].startswith("$argon2id$")
    assert TEACHER_PASSWORD not in all_output(result)
    assert stored["new.teacher@example.com"][1] not in all_output(result)


@pytest.mark.parametrize("flag", ["--password", "--pass", "--passwd"])
def test_a_password_argument_is_refused_by_the_real_process(
    clean_db: str, tmp_path: Path, flag: str
) -> None:
    result = run_cli(
        clean_db, tmp_path, ["create-teacher", "--email", "a@example.com", flag, TEACHER_PASSWORD]
    )

    assert result.returncode == 2
    assert accounts(clean_db) == {}
