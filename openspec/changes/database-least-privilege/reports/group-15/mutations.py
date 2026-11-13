"""Mutations of the task 15.2 controls, applied to a COPY of the code (never to the repository).

usage:
  python mutations.py check <backend dir>
  python mutations.py list
  python mutations.py apply <index> <backend copy>

Each entry removes or weakens one control; the listed tests must fail. A mutant that no test
notices is reported as SURVIVED by the runner. Contract text (docs/api-spec.yml) is not mutated:
the harness copies only `backend/`, and the contract tests read `docs/`.
"""

import sys
from pathlib import Path

STARTUP_UNIT = "tests/unit/test_superuser_refusal.py"
STARTUP_REAL = "tests/integration/test_db_roles_startup.py"
IDENTITY = "tests/integration/test_db_admin_identity.py"
COMMITS_UNIT = "tests/unit/test_endpoint_commits.py"
FAILURES_UNIT = "tests/unit/test_commit_failure_responses.py"
GUARD_UNIT = "tests/unit/test_db_admin_target_guard.py"
ADOPT = "tests/integration/test_db_admin_adopt.py"

MUTATIONS: list[tuple[str, str, str, str, list[str]]] = [
    # --- PG-01
    (
        "the superuser check never refuses",
        "app/core/database.py",
        "    if is_superuser_setting is not False or role_is_superuser is not False:\n",
        "    if False:\n",
        [
            f"{STARTUP_UNIT}::test_the_decision_follows_what_the_server_reports",
            f"{STARTUP_REAL}::test_the_administrator_is_refused",
        ],
    ),
    (
        "the check ignores the roles of the session (reads only the setting)",
        "app/core/database.py",
        "    if is_superuser_setting is not False or role_is_superuser is not False:\n",
        "    if is_superuser_setting is not False:\n",
        [
            f"{STARTUP_UNIT}::test_the_decision_follows_what_the_server_reports",
            f"{STARTUP_REAL}::test_set_role_to_an_unprivileged_role_does_not_hide_the_superuser_session",
        ],
    ),
    (
        "an unverifiable identity is accepted (fails open)",
        "app/core/database.py",
        "        raise SuperuserConnectionError(_UNVERIFIED_MESSAGE) from None\n",
        "        return\n",
        [
            f"{STARTUP_UNIT}::test_an_unreachable_database_fails_closed_without_leaking_the_error",
            f"{STARTUP_REAL}::test_an_unreachable_database_is_refused_without_leaking_the_address",
        ],
    ),
    (
        "the API entry point does not check",
        "app/main.py",
        "        assert_restricted_database_role(app.state.engine)\n    return app\n",
        "        pass\n    return app\n",
        [
            f"{STARTUP_UNIT}::test_the_api_entry_point_checks_the_identity",
            f"{STARTUP_REAL}::test_the_api_process_refuses_to_start_as_the_administrator",
        ],
    ),
    (
        "the worker main does not enforce the check",
        "app/worker.py",
        "    return run_worker(settings, handle_signals=True, enforce_database_identity=True)\n",
        "    return run_worker(settings, handle_signals=True, enforce_database_identity=False)\n",
        [
            f"{STARTUP_UNIT}::test_the_worker_main_enforces_the_check",
            f"{STARTUP_REAL}::test_the_worker_process_refuses_to_start_as_the_administrator",
        ],
    ),
    (
        "the test-only exception is accepted in any environment",
        "app/core/config.py",
        '        if self.allow_superuser_database_role and self.app_env != "test":\n',
        "        if False:\n",
        [f"{STARTUP_UNIT}::test_the_exception_is_rejected_outside_the_test_environment"],
    ),
    # --- PG-02
    (
        "db-migrate does not check the identity",
        "app/db_admin/migrate.py",
        '    require_identity(migrator_url, names.migrator, "db-migrate")\n',
        "",
        [f"{IDENTITY}::test_migrate_as_the_administrator_is_refused_before_any_ddl"],
    ),
    (
        "db-migrate --downgrade does not check the identity",
        "app/db_admin/migrate.py",
        '    require_identity(migrator_url, names.migrator, "db-migrate --downgrade")\n',
        "",
        [f"{IDENTITY}::test_downgrade_as_the_administrator_changes_nothing"],
    ),
    (
        "db-verify does not check the identity",
        "app/db_admin/verify.py",
        '        check_identity(conn, names.migrator, "db-verify")\n',
        "",
        [f"{IDENTITY}::test_verify_as_the_administrator_is_refused"],
    ),
    (
        "the identity check accepts any user",
        "app/db_admin/connection.py",
        "    if row is None or row[0] != expected or row[1] != expected:\n",
        "    if row is None:\n",
        [
            f"{IDENTITY}::test_migrate_as_the_administrator_is_refused_before_any_ddl",
            f"{IDENTITY}::test_migrate_as_another_role_is_refused_before_any_ddl",
        ],
    ),
    # --- F-1, F-2
    (
        "DELETE of a document commits with a bare commit()",
        "app/api/v1/endpoints/documents.py",
        "    commit_or_rollback(db)  # the deletion is durable before the 204 is built (TD-039)\n",
        "    db.commit()  # the deletion is durable before the 204 is built (TD-039)\n",
        [
            f"{COMMITS_UNIT}::test_a_refused_commit_rolls_back_and_never_returns_a_response",
            f"{FAILURES_UNIT}::test_a_handler_that_stores_something_commits_with_the_shared_helper",
        ],
    ),
    (
        "the shared helper no longer rolls back",
        "app/api/transaction.py",
        "    except Exception:\n        db.rollback()\n        raise\n",
        "    except Exception:\n        raise\n",
        [f"{COMMITS_UNIT}::test_a_refused_commit_rolls_back_and_never_returns_a_response"],
    ),
    (
        "a lost connection is no longer a 503",
        "app/core/handlers.py",
        "    app.add_exception_handler(OperationalError, _database_unavailable_handler)\n",
        "",
        [f"{FAILURES_UNIT}::test_a_connection_lost_at_commit_is_a_503_with_the_fixed_body"],
    ),
    (
        "a refused write is reported as a 503",
        "app/core/handlers.py",
        "    app.add_exception_handler(OperationalError, _database_unavailable_handler)\n",
        "    app.add_exception_handler(OperationalError, _database_unavailable_handler)\n"
        "    from sqlalchemy.exc import ProgrammingError\n\n"
        "    app.add_exception_handler(ProgrammingError, _database_unavailable_handler)\n",
        [f"{FAILURES_UNIT}::test_a_write_refused_at_commit_is_a_500_with_the_fixed_body"],
    ),
    # --- PG-07
    (
        "db-bootstrap accepts a system database",
        "app/db_admin/bootstrap.py",
        '    refuse_system_database(database, "db-bootstrap")  # refuse before any connection\n',
        "",
        [f"{GUARD_UNIT}::test_bootstrap_refuses_a_system_database_before_connecting"],
    ),
    (
        "db-adopt accepts a system database",
        "app/db_admin/adopt.py",
        '    refuse_system_database(database, "db-adopt")\n',
        "",
        [f"{GUARD_UNIT}::test_adopt_refuses_a_system_database_before_connecting"],
    ),
    (
        "the rollback accepts a system database",
        "app/db_admin/adopt.py",
        '    refuse_system_database(database, "db-adopt --rollback")\n',
        "",
        [f"{GUARD_UNIT}::test_the_rollback_refuses_a_system_database_before_connecting"],
    ),
    (
        "the rollback reassigns in another database than the named one",
        "app/db_admin/adopt.py",
        "        with connect(admin_url, database=database) as scoped:\n"
        '            statement = f"REASSIGN OWNED BY',
        '        with connect(admin_url, database="postgres") as scoped:\n'
        '            statement = f"REASSIGN OWNED BY',
        [f"{ADOPT}::test_the_rollback_acts_only_on_the_named_database_and_reports_the_other"],
    ),
    (
        "the rollback does not report the other databases",
        "app/db_admin/adopt.py",
        "            tuple(name for name in _owned_by_database(conn, names.migrator) if name != database)\n",
        "            tuple(name for name in _owned_by_database(conn, names.migrator) if False)\n",
        [f"{ADOPT}::test_the_rollback_acts_only_on_the_named_database_and_reports_the_other"],
    ),
    (
        "the rollback accepts a database that does not exist",
        "app/db_admin/adopt.py",
        "    if database not in databases:\n",
        "    if False:\n",
        [f"{ADOPT}::test_the_rollback_refuses_a_database_that_does_not_exist"],
    ),
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def check(backend: Path) -> int:
    missing = 0
    for index, (label, rel, old, _new, _targets) in enumerate(MUTATIONS):
        found = _read(backend / rel).count(old)
        if found != 1:
            print(f"{index}: {found} occurrences of the text to mutate: {label}")
            missing += 1
    print(f"{len(MUTATIONS)} mutations, {missing} problem(s)")
    return 1 if missing else 0


def main() -> int:
    command = sys.argv[1]
    if command == "list":
        for index, (label, *_rest) in enumerate(MUTATIONS):
            print(f"{index}\t{label}")
        return 0
    if command == "check":
        return check(Path(sys.argv[2]))
    if command == "apply":
        index, backend = int(sys.argv[2]), Path(sys.argv[3])
        _label, rel, old, new, targets = MUTATIONS[index]
        path = backend / rel
        text = _read(path)
        assert text.count(old) == 1, "the text to mutate must appear exactly once"
        path.write_text(text.replace(old, new), encoding="utf-8")
        print(" ".join(targets))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
