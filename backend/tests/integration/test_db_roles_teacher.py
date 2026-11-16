"""Teacher provisioning separated at database level (change `database-least-privilege`, 8.2).

Runs the registration endpoint under the real application role and the administrative command under
the real CLI role on a database prepared like production (bootstrap, migrations to head, grants).
"""

import io
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.cli import run
from app.core.config import CliSettings
from app.core.database import create_db_engine, create_session_factory
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from tests.db_admin_support import Cluster
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)
from tests.db_roles_support import as_role, sqlstate_of
from tests.db_roles_support import own_database as own_database
from tests.integration.helpers import FAST_PASSWORDS, build_app

REGISTER = "/api/v1/auth/register"
PASSWORD = "a-very-long-password"


@contextmanager
def api_client(cluster: Cluster, database: str) -> Iterator[TestClient]:
    with TestClient(
        build_app(cluster.role_url("app", database)), raise_server_exceptions=False
    ) as c:
        yield c


def stored_role(cluster: Cluster, database: str, email: str) -> str | None:
    with cluster.admin_connection(database) as conn:
        row = conn.execute("SELECT role::text FROM users WHERE email = %s", (email,)).fetchone()
    return None if row is None else str(row[0])


def run_cli(
    cluster: Cluster,
    database: str,
    argv: list[str],
    stdin: str = "",
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    url = cluster.role_url("cli", database)
    engine = create_db_engine(url)
    out: list[str] = []
    err: list[str] = []
    try:
        code = run(
            argv,
            settings=CliSettings(cli_database_url=url, app_env="test"),
            session_factory=create_session_factory(engine),
            passwords=FAST_PASSWORDS,
            env=env or {},
            stdin=io.StringIO(stdin),
            prompt_password=lambda _label: PASSWORD,
            out=out.append,
            err=err.append,
        )
    finally:
        engine.dispose()
    return code, "\n".join(out), "\n".join(err)


# ---- public registration under the application role -------------------------------------------


def test_public_registration_stores_a_student_under_the_application_role(
    cluster: Cluster, own_database: str
) -> None:
    with api_client(cluster, own_database) as client:
        response = client.post(
            REGISTER, json={"name": "Ana", "email": "ana@example.com", "password": PASSWORD}
        )

    assert response.status_code == 201
    assert response.json()["role"] == "student"
    assert stored_role(cluster, own_database, "ana@example.com") == "student"


def test_a_payload_that_asks_for_the_teacher_role_still_creates_a_student(
    cluster: Cluster, own_database: str
) -> None:
    with api_client(cluster, own_database) as client:
        response = client.post(
            REGISTER,
            json={
                "name": "Eve",
                "email": "eve@example.com",
                "password": PASSWORD,
                "role": "teacher",
            },
        )

    assert response.status_code == 201  # the unknown field is dropped, never honoured
    assert response.json()["role"] == "student"
    assert stored_role(cluster, own_database, "eve@example.com") == "student"


def test_the_application_role_cannot_insert_a_teacher_or_change_a_role(
    cluster: Cluster, own_database: str
) -> None:
    engine = create_db_engine(cluster.role_url("app", own_database))
    try:
        with Session(engine) as session, pytest.raises(ProgrammingError) as caught:
            UserRepository(session).add(
                User(
                    name="T",
                    email="forged-teacher@example.com",
                    password_hash="h",
                    role=UserRole.TEACHER,
                )
            )
        assert getattr(caught.value.orig, "sqlstate", None) == "42501"
    finally:
        engine.dispose()
    with as_role(cluster, "app", own_database) as conn:
        assert sqlstate_of(conn, "UPDATE users SET role = 'teacher'") == "42501"
        assert (
            sqlstate_of(
                conn,
                "INSERT INTO users (name, email, password_hash, role) "
                "VALUES ('T', 'forged@example.com', 'h', 'teacher')",
            )
            == "42501"
        )
    assert stored_role(cluster, own_database, "forged-teacher@example.com") is None
    assert stored_role(cluster, own_database, "forged@example.com") is None


# ---- administrative provisioning under the CLI role ---------------------------------------------


def test_the_cli_role_creates_a_teacher_and_prints_no_secret(
    cluster: Cluster, own_database: str
) -> None:
    code, out, err = run_cli(
        cluster,
        own_database,
        ["create-teacher", "--email", "Teach@Example.com", "--name", "Teach", "--password-stdin"],
        stdin=PASSWORD + "\n",
    )

    assert code == 0, err
    assert stored_role(cluster, own_database, "teach@example.com") == "teacher"
    assert PASSWORD not in out + err and "argon2" not in out + err


def test_a_duplicate_teacher_changes_nothing_under_the_cli_role(
    cluster: Cluster, own_database: str
) -> None:
    args = ["create-teacher", "--email", "dup@example.com", "--password-stdin"]
    assert run_cli(cluster, own_database, args, stdin=PASSWORD + "\n")[0] == 0
    with cluster.admin_connection(own_database) as conn:
        before = conn.execute("SELECT count(*) FROM users").fetchone()

    code, _, err = run_cli(cluster, own_database, args, stdin=PASSWORD + "\n")

    assert code == 1 and "already exists" in err
    with cluster.admin_connection(own_database) as conn:
        assert conn.execute("SELECT count(*) FROM users").fetchone() == before


def test_the_seed_follows_the_same_path_under_the_cli_role(
    cluster: Cluster, own_database: str
) -> None:
    env = {
        "SEED_TEACHER_EMAIL": "seed.teacher@example.com",
        "SEED_TEACHER_PASSWORD": "teacher-demo-password",
        "SEED_STUDENT_EMAIL": "seed.student@example.com",
        "SEED_STUDENT_PASSWORD": "student-demo-password",
    }

    code, _, err = run_cli(cluster, own_database, ["seed"], env=env)

    assert code == 0, err
    assert stored_role(cluster, own_database, "seed.teacher@example.com") == "teacher"
    assert stored_role(cluster, own_database, "seed.student@example.com") == "student"


def test_the_cli_role_is_limited_to_creating_and_reading_accounts(
    cluster: Cluster, own_database: str
) -> None:
    refused = [
        "UPDATE users SET role = 'teacher'",
        "UPDATE users SET password_hash = 'x'",
        "DELETE FROM users",
        "SELECT * FROM subjects",
        "INSERT INTO subjects (name, teacher_id) VALUES ('x', gen_random_uuid())",
        "SELECT * FROM documents",
        "SELECT id FROM document_chunks",
        "SELECT * FROM ingestion_jobs",
        "CREATE TABLE public.cli_forged (id int)",
    ]
    with as_role(cluster, "cli", own_database) as conn:
        for sql in refused:
            assert sqlstate_of(conn, sql) == "42501", sql
        assert sqlstate_of(conn, "SELECT id, email, role FROM users") is None


def test_the_roles_do_not_share_credentials(cluster: Cluster, own_database: str) -> None:
    assert cluster.role_url("cli", own_database) != cluster.role_url("app", own_database)
    with as_role(cluster, "cli", own_database) as conn:
        row = conn.execute("SELECT current_user").fetchone()
    assert row == (cluster.names.cli,)
