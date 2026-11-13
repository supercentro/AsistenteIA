"""Glue between the CLI arguments and the administration commands (task 4).

Each command reads only its own settings: the bootstrap and the adoption need the administrator
URL and the role passwords (`.env.roles`), `db-migrate` and `db-grants` the migrator URL
(`.env.migrate`), `db-verify` the migrator URL and the four passwords. None needs the API
settings. Errors become one line without values and exit code 1.
"""

import argparse
from collections.abc import Callable

import psycopg
from alembic.util.exc import CommandError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import (
    ConfigurationError,
    load_migration_settings,
    load_roles_settings,
    load_verify_settings,
)
from app.db_admin.adopt import adopt, rollback_adoption
from app.db_admin.bootstrap import bootstrap
from app.db_admin.errors import DbAdminError
from app.db_admin.grants import apply_grants
from app.db_admin.migrate import downgrade, migrate
from app.db_admin.names import DEFAULT_NAMES, RolePasswords
from app.db_admin.verify import render_findings, verify


def run_database_command(
    args: argparse.Namespace, out: Callable[[str], None], err: Callable[[str], None]
) -> int:
    try:
        return _dispatch(args, out)
    except (ConfigurationError, DbAdminError) as exc:
        err(f"Error: {exc}")
        return 1
    except (psycopg.Error, SQLAlchemyError, CommandError) as exc:
        # Driver and Alembic messages can carry statements or values: name the type only.
        code = getattr(exc, "sqlstate", None) or getattr(
            getattr(exc, "orig", None), "sqlstate", None
        )
        err(f"Error: {type(exc).__name__} (SQLSTATE {code or 'none'})")
        return 1


def _dispatch(args: argparse.Namespace, out: Callable[[str], None]) -> int:
    command = str(args.command)
    if command == "db-bootstrap":
        roles = load_roles_settings()
        report = bootstrap(
            roles.admin_database_url.get_secret_value(),
            RolePasswords(
                migrator=roles.db_migrator_password.get_secret_value(),
                app=roles.db_app_password.get_secret_value(),
                worker=roles.db_worker_password.get_secret_value(),
                cli=roles.db_cli_password.get_secret_value(),
            ),
            database=str(args.database),
        )
        for line in report.summary():
            out(line)
        return 1 if report.ownership_drift else 0  # drift is reported, not repaired: not a success
    if command == "db-adopt":
        if args.remove_roles and not args.rollback:
            raise DbAdminError("--remove-roles only makes sense with --rollback")
        roles = load_roles_settings()
        admin_url = roles.admin_database_url.get_secret_value()
        if args.rollback and not args.apply:
            out(
                "dry run: --rollback would REASSIGN OWNED BY the migrator to the administrator in "
                "every database"
                + (" and then drop the four roles" if args.remove_roles else "")
                + "; nothing was changed, add --apply to do it"
            )
            return 0
        if args.rollback:
            rollback = rollback_adoption(
                admin_url,
                database=str(args.database),
                names=DEFAULT_NAMES,
                remove_roles=bool(args.remove_roles),
            )
            for line in rollback.summary():
                out(line)
            return 0
        adoption = adopt(
            admin_url, database=str(args.database), names=DEFAULT_NAMES, apply=bool(args.apply)
        )
        for line in adoption.summary():
            out(line)
        return 0
    if command == "db-migrate":
        url = load_migration_settings().migration_database_url.get_secret_value()
        if args.downgrade:
            downgrade(url, str(args.downgrade), names=DEFAULT_NAMES)
            out(f"downgraded to {args.downgrade} (no grants applied)")
        else:
            migrate(url, names=DEFAULT_NAMES)
            out("migrated to head and applied the privilege grants")
        return 0
    if command == "db-grants":
        url = load_migration_settings().migration_database_url.get_secret_value()
        out(
            f"applied {apply_grants(url, names=DEFAULT_NAMES)} grant statement(s) in one transaction"  # noqa: E501
        )
        return 0
    if command == "db-verify":
        settings = load_verify_settings()
        findings = verify(
            settings.migration_database_url.get_secret_value(),
            RolePasswords(
                migrator=settings.db_migrator_password.get_secret_value(),
                app=settings.db_app_password.get_secret_value(),
                worker=settings.db_worker_password.get_secret_value(),
                cli=settings.db_cli_password.get_secret_value(),
            ),
            names=DEFAULT_NAMES,
        )
        out(render_findings(findings))
        return 1 if findings else 0
    raise DbAdminError("unknown database command")
