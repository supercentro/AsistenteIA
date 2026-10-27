"""Administrative commands. Run with `python -m app.cli <command>`.

These commands are the only way to create teacher accounts; nothing here is reachable over HTTP.
Passwords are never accepted as arguments and never printed.
"""

import argparse
import getpass
import os
import sys
from collections.abc import Callable, Mapping
from typing import NoReturn, TextIO

from dotenv import dotenv_values
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import ConfigurationError, Settings, load_settings
from app.core.database import create_db_engine, create_session_factory
from app.core.errors import ConflictError
from app.core.security import PasswordService
from app.models.user import UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    ensure_no_control_characters,
    normalize_email,
)
from app.services.user_admin_service import UserAdminService

SEED_VARIABLES = (
    "SEED_TEACHER_EMAIL",
    "SEED_TEACHER_PASSWORD",
    "SEED_STUDENT_EMAIL",
    "SEED_STUDENT_PASSWORD",
)
SEED_ALLOWED_ENVIRONMENTS = ("development", "test")
PASSWORD_RULE = f"must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters long"

_email_adapter: TypeAdapter[str] = TypeAdapter(EmailStr)


class CliError(Exception):
    """A user-facing failure; the message never contains passwords or hashes."""


def _valid_email(raw: str, label: str) -> str:
    try:
        return normalize_email(_email_adapter.validate_python(raw.strip()))
    except (ValidationError, ValueError):
        raise CliError(f"{label} is not a valid email address") from None


def _valid_password(password: str, label: str) -> str:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise CliError(f"{label} {PASSWORD_RULE}")
    return password


class SafeArgumentParser(argparse.ArgumentParser):
    """Argument errors never repeat supplied values (a typed password stays unprinted)."""

    def error(self, message: str) -> NoReturn:
        if message.startswith("unrecognized arguments"):
            message = (
                "unrecognized arguments (values hidden; passwords are never accepted as arguments)"
            )
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(prog="python -m app.cli", allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)

    teacher = commands.add_parser(
        "create-teacher", help="create a teacher account", allow_abbrev=False
    )
    teacher.add_argument("--email", required=True)
    teacher.add_argument("--name", help="defaults to the part of the email before '@'")
    teacher.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the password from the first line of standard input instead of prompting",
    )

    commands.add_parser(
        "seed",
        help="create one demo teacher and one demo student from SEED_* variables "
        "(development and test only)",
        allow_abbrev=False,
    )
    return parser


def _create_teacher(
    args: argparse.Namespace,
    session: Session,
    passwords: PasswordService,
    stdin: TextIO,
    prompt_password: Callable[[str], str],
    out: Callable[[str], None],
) -> None:
    email = _valid_email(args.email, "--email")
    name = (args.name or email.split("@", 1)[0]).strip()
    try:
        ensure_no_control_characters(name)
    except ValueError:
        raise CliError("--name must not contain control or direction characters") from None
    if not 1 <= len(name) <= 100:
        raise CliError("--name must be 1-100 characters long")

    if args.password_stdin:
        password = stdin.readline().rstrip("\r\n")
    else:
        password = prompt_password("Password: ")
        if prompt_password("Repeat password: ") != password:
            raise CliError("The passwords do not match")
    _valid_password(password, "The password")

    service = UserAdminService(UserRepository(session), passwords)
    if service.exists(email):
        raise CliError("An account with this email already exists; nothing was changed")
    try:
        user = service.create_account(name, email, password, UserRole.TEACHER)
    except ConflictError:
        raise CliError("An account with this email already exists; nothing was changed") from None
    session.commit()
    out(f"Created teacher id={user.id} email={user.email}")


def _seed(
    settings: Settings,
    session: Session,
    passwords: PasswordService,
    env: Mapping[str, str],
    out: Callable[[str], None],
) -> None:
    if settings.app_env not in SEED_ALLOWED_ENVIRONMENTS:
        raise CliError(f"seed is disabled when APP_ENV={settings.app_env}")

    values = {name: env.get(name) for name in SEED_VARIABLES}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise CliError("Missing seed variables: " + ", ".join(missing))

    teacher_email = _valid_email(str(values["SEED_TEACHER_EMAIL"]), "SEED_TEACHER_EMAIL")
    student_email = _valid_email(str(values["SEED_STUDENT_EMAIL"]), "SEED_STUDENT_EMAIL")
    if teacher_email == student_email:
        raise CliError("SEED_TEACHER_EMAIL and SEED_STUDENT_EMAIL must differ")
    teacher_password = _valid_password(
        str(values["SEED_TEACHER_PASSWORD"]), "SEED_TEACHER_PASSWORD"
    )
    student_password = _valid_password(
        str(values["SEED_STUDENT_PASSWORD"]), "SEED_STUDENT_PASSWORD"
    )

    service = UserAdminService(UserRepository(session), passwords)
    plan = (
        ("teacher", "Demo Teacher", teacher_email, teacher_password, UserRole.TEACHER),
        ("student", "Demo Student", student_email, student_password, UserRole.STUDENT),
    )
    for label, name, email, password, role in plan:
        if service.exists(email):
            out(f"Skipped {label}: an account with this email already exists")
            continue
        user = service.create_account(name, email, password, role)
        out(f"Created {label} id={user.id}")
    session.commit()


def run(
    argv: list[str],
    *,
    settings: Settings,
    session_factory: sessionmaker[Session],
    passwords: PasswordService,
    env: Mapping[str, str],
    stdin: TextIO,
    prompt_password: Callable[[str], str],
    out: Callable[[str], None],
    err: Callable[[str], None],
) -> int:
    """Execute one command and return the process exit code (argparse errors exit with 2)."""
    args = build_parser().parse_args(argv)
    session = session_factory()
    try:
        if args.command == "create-teacher":
            _create_teacher(args, session, passwords, stdin, prompt_password, out)
        else:
            _seed(settings, session, passwords, env, out)
        return 0
    except CliError as exc:
        session.rollback()
        err(f"Error: {exc}")
        return 1
    finally:
        session.close()


def main() -> int:
    try:
        settings = load_settings()
    except ConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    # Values from backend/.env sit below the real environment, like for the application settings.
    env = {k: v for k, v in dotenv_values(".env").items() if v is not None}
    env.update(os.environ)
    engine = create_db_engine(settings.database_url, settings.db_connect_timeout_seconds)
    try:
        return run(
            sys.argv[1:],
            settings=settings,
            session_factory=create_session_factory(engine),
            passwords=PasswordService(),
            env=env,
            stdin=sys.stdin,
            prompt_password=getpass.getpass,
            out=print,
            err=lambda message: print(message, file=sys.stderr),
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
