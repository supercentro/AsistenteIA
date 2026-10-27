import io
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from sqlalchemy import text

from app.cli import run
from app.core.config import Settings
from app.core.database import create_db_engine, create_session_factory
from tests.integration.helpers import FAST_PASSWORDS, MakeUser, build_settings

STRONG = "a-strong-password-1"
SEED_ENV = {
    "SEED_TEACHER_EMAIL": "Teacher.Demo@Example.com",
    "SEED_TEACHER_PASSWORD": "teacher-demo-password",
    "SEED_STUDENT_EMAIL": "student.demo@example.com",
    "SEED_STUDENT_PASSWORD": "student-demo-password",
}


@dataclass
class Cli:
    database_url: str
    out: list[str] = field(default_factory=list)
    err: list[str] = field(default_factory=list)

    def __call__(
        self,
        argv: list[str],
        *,
        settings: Settings | None = None,
        env: Mapping[str, str] | None = None,
        stdin: str = "",
        prompts: Callable[[str], str] | None = None,
    ) -> int:
        engine = create_db_engine(self.database_url)
        try:
            return run(
                argv,
                settings=settings or build_settings(self.database_url, app_env="test"),
                session_factory=create_session_factory(engine),
                passwords=FAST_PASSWORDS,
                env=env or {},
                stdin=io.StringIO(stdin),
                prompt_password=prompts or (lambda _label: STRONG),
                out=self.out.append,
                err=self.err.append,
            )
        finally:
            engine.dispose()

    @property
    def output(self) -> str:
        return "\n".join(self.out + self.err)


@pytest.fixture
def cli(clean_db: str) -> Cli:
    return Cli(clean_db)


def accounts(database_url: str) -> list[tuple[str, str, str]]:
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT email, role::text, password_hash FROM users ORDER BY email")
            )
            return [(r[0], r[1], r[2]) for r in rows]
    finally:
        engine.dispose()


# ------------------------------------------------------------ create-teacher


def test_create_teacher_stores_a_teacher_with_an_argon2id_hash(cli: Cli, clean_db: str) -> None:
    code = cli(["create-teacher", "--email", "Prof@Example.com", "--name", "Prof"])

    assert code == 0
    [(email, role, stored)] = accounts(clean_db)
    assert (email, role) == ("prof@example.com", "teacher")
    assert stored.startswith("$argon2id$")
    assert STRONG not in stored


def test_create_teacher_output_never_contains_password_or_hash(cli: Cli, clean_db: str) -> None:
    cli(["create-teacher", "--email", "prof@example.com"])

    [(_, _, stored)] = accounts(clean_db)
    assert STRONG not in cli.output
    assert stored not in cli.output
    assert "argon2" not in cli.output
    assert "prof@example.com" in cli.output


def test_create_teacher_name_defaults_to_the_email_local_part(cli: Cli, clean_db: str) -> None:
    cli(["create-teacher", "--email", "maria.lopez@example.com"])

    engine = create_db_engine(clean_db)
    with engine.connect() as conn:
        name = conn.execute(text("SELECT name FROM users")).scalar_one()
    engine.dispose()
    assert name == "maria.lopez"


def test_create_teacher_reads_the_password_from_stdin(cli: Cli, clean_db: str) -> None:
    def fail(_label: str) -> str:
        raise AssertionError("the interactive prompt must not be used with --password-stdin")

    code = cli(
        ["create-teacher", "--email", "prof@example.com", "--password-stdin"],
        stdin="piped-password-123\n",
        prompts=fail,
    )

    assert code == 0
    engine = create_db_engine(clean_db)
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT password_hash FROM users")).scalar_one()
    engine.dispose()
    assert FAST_PASSWORDS.verify("piped-password-123", stored) is True


def test_create_teacher_rejects_a_short_password_and_creates_nothing(
    cli: Cli, clean_db: str
) -> None:
    code = cli(["create-teacher", "--email", "prof@example.com"], prompts=lambda _l: "short")

    assert code != 0
    assert accounts(clean_db) == []


def test_create_teacher_rejects_an_overlong_password(cli: Cli, clean_db: str) -> None:
    code = cli(["create-teacher", "--email", "prof@example.com"], prompts=lambda _l: "x" * 129)

    assert code != 0
    assert accounts(clean_db) == []


def test_create_teacher_rejects_mismatched_confirmation(cli: Cli, clean_db: str) -> None:
    answers = iter(["first-password-123", "different-password-123"])

    code = cli(["create-teacher", "--email", "prof@example.com"], prompts=lambda _l: next(answers))

    assert code != 0
    assert accounts(clean_db) == []


def test_create_teacher_rejects_an_invalid_email(cli: Cli, clean_db: str) -> None:
    assert cli(["create-teacher", "--email", "not-an-email"]) != 0
    assert accounts(clean_db) == []


@pytest.mark.parametrize("existing_role", ["student", "teacher"])
def test_create_teacher_never_touches_an_existing_account(
    cli: Cli, make_user: MakeUser, clean_db: str, existing_role: str
) -> None:
    from app.models.user import UserRole

    make_user("taken@example.com", UserRole(existing_role))
    before = accounts(clean_db)

    code = cli(["create-teacher", "--email", "TAKEN@example.com"])

    assert code != 0
    assert accounts(clean_db) == before


def test_password_cannot_be_passed_as_an_argument(cli: Cli, clean_db: str) -> None:
    with pytest.raises(SystemExit) as exc:
        cli(["create-teacher", "--email", "prof@example.com", "--password", STRONG])
    assert exc.value.code == 2

    with pytest.raises(SystemExit):
        cli(["create-teacher", "--email", "prof@example.com", "--pass", STRONG])  # no abbreviations
    assert accounts(clean_db) == []


# ---------------------------------------------------------------------- seed


def test_seed_creates_one_teacher_and_one_student_and_nothing_else(cli: Cli, clean_db: str) -> None:
    code = cli(["seed"], env=SEED_ENV)

    assert code == 0
    rows = accounts(clean_db)
    assert [(email, role) for email, role, _ in rows] == [
        ("student.demo@example.com", "student"),
        ("teacher.demo@example.com", "teacher"),
    ]
    for _, _, stored in rows:
        assert stored.startswith("$argon2id$")
    engine = create_db_engine(clean_db)
    with engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        }
        assert conn.execute(text("SELECT count(*) FROM users")).scalar_one() == 2
    engine.dispose()
    assert tables <= {"users", "alembic_version"}  # no subjects or any other data


def test_seed_never_prints_passwords_or_hashes(cli: Cli, clean_db: str) -> None:
    cli(["seed"], env=SEED_ENV)

    for secret in ("teacher-demo-password", "student-demo-password", "argon2"):
        assert secret not in cli.output


def test_seed_is_idempotent(cli: Cli, clean_db: str) -> None:
    cli(["seed"], env=SEED_ENV)
    first = accounts(clean_db)

    code = cli(["seed"], env={**SEED_ENV, "SEED_TEACHER_PASSWORD": "a-different-password"})

    assert code == 0
    assert accounts(clean_db) == first  # nothing created, nothing changed (hashes included)


@pytest.mark.parametrize("app_env", ["production"])
def test_seed_refuses_to_run_in_production(cli: Cli, clean_db: str, app_env: str) -> None:
    settings = build_settings(clean_db, app_env=app_env, cors_origins=["https://app.example"])

    code = cli(["seed"], settings=settings, env=SEED_ENV)

    assert code != 0
    assert accounts(clean_db) == []
    assert "production" in cli.output


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_seed_runs_in_development_and_test(cli: Cli, clean_db: str, app_env: str) -> None:
    settings = build_settings(clean_db, app_env=app_env)

    assert cli(["seed"], settings=settings, env=SEED_ENV) == 0


@pytest.mark.parametrize("missing", list(SEED_ENV))
def test_seed_with_a_missing_variable_creates_nothing(
    cli: Cli, clean_db: str, missing: str
) -> None:
    env = {k: v for k, v in SEED_ENV.items() if k != missing}

    code = cli(["seed"], env=env)

    assert code != 0
    assert accounts(clean_db) == []
    assert missing in cli.output


def test_seed_with_no_variables_has_no_built_in_credentials(cli: Cli, clean_db: str) -> None:
    assert cli(["seed"], env={}) != 0
    assert accounts(clean_db) == []


@pytest.mark.parametrize("weak", ["SEED_TEACHER_PASSWORD", "SEED_STUDENT_PASSWORD"])
def test_seed_with_a_weak_password_creates_nothing(cli: Cli, clean_db: str, weak: str) -> None:
    code = cli(["seed"], env={**SEED_ENV, weak: "short"})

    assert code != 0
    assert accounts(clean_db) == []
    assert "short" not in cli.output


def test_seed_with_identical_emails_creates_nothing(cli: Cli, clean_db: str) -> None:
    env = {**SEED_ENV, "SEED_STUDENT_EMAIL": SEED_ENV["SEED_TEACHER_EMAIL"]}

    assert cli(["seed"], env=env) != 0
    assert accounts(clean_db) == []


def test_seed_keeps_an_existing_account_untouched(
    cli: Cli, make_user: MakeUser, clean_db: str
) -> None:
    make_user("student.demo@example.com")
    before = {email: stored for email, _, stored in accounts(clean_db)}

    code = cli(["seed"], env=SEED_ENV)

    after = {email: stored for email, _, stored in accounts(clean_db)}
    assert code == 0
    assert after["student.demo@example.com"] == before["student.demo@example.com"]
    assert "teacher.demo@example.com" in after


# ---------------------------------------------------------------- static rules


def test_env_example_contains_no_default_seed_credentials() -> None:
    example = Path(__file__).resolve().parents[2] / ".env.example"

    for line in example.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*(SEED_[A-Z_]+)\s*=\s*(\S+)", line)
        assert match is None, f"{match.group(1) if match else ''} must not have a default value"


def test_cli_source_has_no_default_credentials() -> None:
    source = (Path(__file__).resolve().parents[2] / "app/cli.py").read_text(encoding="utf-8")

    assert not re.search(r"\.get\([^)]*,\s*['\"]", source), "env lookups must not have defaults"
    assert "getenv" not in source


@pytest.mark.parametrize(
    "name",
    ["a\u2028b", "a\u202eb", "tab\tname", "line\nbreak", "nul\x00name", "n" * 101],
    ids=["line-separator", "bidi-override", "tab", "newline", "nul", "too-long"],
)
def test_create_teacher_rejects_unsafe_names(cli: Cli, clean_db: str, name: str) -> None:
    code = cli(["create-teacher", "--email", "prof@example.com", "--name", name])

    assert code != 0
    assert accounts(clean_db) == []


def test_unsupported_arguments_are_not_echoed(cli: Cli, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli(["create-teacher", "--email", "a@example.com", "--password", "Hunter2-Secret!"])

    captured = capsys.readouterr()
    assert exc.value.code == 2
    assert "Hunter2-Secret!" not in captured.out + captured.err
