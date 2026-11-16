"""Mutations of the group 4 commands (task 4.6), applied to a COPY of the code, never to the repo.

usage:
  python mutations.py check <backend dir>              every `old` text exists exactly once
  python mutations.py list                             one line per mutation: index, label
  python mutations.py apply <index> <backend copy>     edit the copy, print the test targets

A mutation is "caught" when the listed tests fail on the edited copy; the harness also runs the
same tests on the unedited copy first to prove they pass.
"""

import sys
from pathlib import Path

# (label, file, old text, new text, pytest targets relative to the backend directory)
UNIT_SQL = "tests/unit/test_db_admin_sql.py"
UNIT_CONN = "tests/unit/test_db_admin_connection.py"
BOOT = "tests/integration/test_db_admin_bootstrap.py"
ADOPT = "tests/integration/test_db_admin_adopt.py"
GRANTS = "tests/integration/test_db_admin_grants.py"
VERIFY = "tests/integration/test_db_admin_verify.py"

MUTATIONS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "bootstrap: RESET ALL removed from the role steps",
        "app/db_admin/bootstrap.py",
        'f"ALTER ROLE {quoted} RESET ALL"',
        'f"ALTER ROLE {quoted} SET lock_timeout = 0"',
        [UNIT_SQL, f"{BOOT}::test_persistent_role_settings_and_memberships_are_healed"],
    ),
    (
        "bootstrap: memberships are no longer revoked",
        "app/db_admin/bootstrap.py",
        "\"EXECUTE pg_catalog.format('REVOKE %I FROM %I', r.grp, r.member); \"",
        '"NULL; "',
        [f"{BOOT}::test_persistent_role_settings_and_memberships_are_healed"],
    ),
    (
        "bootstrap: PUBLIC is not closed on the other databases",
        "app/db_admin/bootstrap.py",
        "        for name in databases\n    ]",
        "        for name in []\n    ]",
        [UNIT_SQL, f"{BOOT}::test_public_is_closed_on_every_database_including_the_templates"],
    ),
    (
        "bootstrap: schema public stays open to PUBLIC",
        "app/db_admin/bootstrap.py",
        'f"REVOKE ALL ON SCHEMA {schema} FROM PUBLIC"',
        'f"GRANT USAGE ON SCHEMA {schema} TO PUBLIC"',
        [UNIT_SQL, f"{BOOT}::test_schema_public_extension_and_default_privileges"],
    ),
    (
        "bootstrap: new functions of the migrator are executable by PUBLIC",
        "app/db_admin/bootstrap.py",
        '"REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"',
        '"GRANT EXECUTE ON FUNCTIONS TO PUBLIC"',
        [UNIT_SQL, f"{BOOT}::test_schema_public_extension_and_default_privileges"],
    ),
    (
        "bootstrap: NOSUPERUSER dropped from the role attributes",
        "app/db_admin/bootstrap.py",
        '_ATTRIBUTES = "LOGIN NOSUPERUSER NOCREATEDB',
        '_ATTRIBUTES = "LOGIN NOCREATEDB',
        [UNIT_SQL, f"{BOOT}::test_roles_are_created_with_minimal_attributes_and_limits"],
    ),
    (
        "sql: a sensitive step shows its statement",
        "app/db_admin/sql.py",
        "return self.description if self.sensitive else self.sql",
        "return self.sql",
        [UNIT_SQL],
    ),
    (
        "sql: identifiers are no longer validated",
        "app/db_admin/sql.py",
        "if not IDENTIFIER.fullmatch(name):",
        "if False:",
        [UNIT_SQL, f"{BOOT}::test_a_bad_database_name_is_refused_before_any_connection"],
    ),
    (
        "connection: the search_path=pg_catalog option is removed",
        "app/db_admin/connection.py",
        'options = ["-c search_path=pg_catalog"]',
        'options = ["-c application_name=x"]',
        [UNIT_CONN],
    ),
    (
        "connection: errors include the driver message",
        "app/db_admin/connection.py",
        "f\"(SQLSTATE {exc.sqlstate or 'none'}, {type(exc).__name__})\"",
        "f\"(SQLSTATE {exc.sqlstate or 'none'}, {exc})\"",
        [UNIT_CONN],
    ),
    (
        "grants: not atomic (autocommit)",
        "app/db_admin/grants.py",
        "with connect(migrator_url, autocommit=False, lock_timeout_ms=10_000) as conn:",
        "with connect(migrator_url, autocommit=True, lock_timeout_ms=10_000) as conn:",
        [f"{GRANTS}::test_a_failure_in_the_grants_rolls_back_every_statement"],
    ),
    (
        "grants: the table-level revoke from the runtime roles is skipped",
        "app/db_admin/grants.py",
        "            statements.append(f\"REVOKE ALL ON TABLE {quoted_table} FROM {quoted_roles[logical]}\")",
        "            pass",
        [UNIT_SQL],
    ),
    (
        "adopt: sessions on the database are not checked",
        "app/db_admin/adopt.py",
        "            sessions = _blocking_sessions(conn, names, ignore_application_names)",
        "            sessions = []",
        [
            f"{ADOPT}::test_adoption_is_refused_while_a_runtime_session_exists_and_nothing_changes",
            f"{ADOPT}::test_adoption_is_refused_while_the_administrator_still_serves_the_database",
        ],
    ),
    (
        "adopt: unexpected objects are ignored",
        "app/db_admin/adopt.py",
        "            unexpected = _unexpected_objects(conn, admin, names.migrator)",
        "            unexpected = []",
        [f"{ADOPT}::test_adoption_refuses_unexpected_objects_and_changes_nothing"],
    ),
    (
        "adopt: not atomic (autocommit)",
        "app/db_admin/adopt.py",
        "admin_url, database=database, autocommit=False, lock_timeout_ms=lock_timeout_ms",
        "admin_url, database=database, autocommit=True, lock_timeout_ms=lock_timeout_ms",
        [f"{ADOPT}::test_adoption_is_atomic_when_a_statement_fails"],
    ),
    (
        "adopt: roles are dropped even while they own objects (DROP OWNED before REASSIGN)",
        "app/db_admin/adopt.py",
        "            owned = _owned_count(conn, role)",
        "            owned = 0",
        [f"{ADOPT}::test_removing_the_roles_is_refused_while_they_own_objects"],
    ),
    (
        "verify: the login probe is skipped",
        "app/db_admin/verify.py",
        "    findings.extend(_login_probe(migrator_url, passwords, names))\n",
        "",
        [f"{VERIFY}::test_each_drift_is_reported_with_the_check_that_found_it"],
    ),
    (
        "verify: extra privileges are not reported",
        "app/db_admin/verify.py",
        "                if extra:\n",
        "                if False:\n",
        [f"{VERIFY}::test_each_drift_is_reported_with_the_check_that_found_it"],
    ),
    (
        "verify: wrong owners are not reported",
        "app/db_admin/verify.py",
        "        if owner != names.migrator\n",
        "        if False\n",
        [f"{VERIFY}::test_each_drift_is_reported_with_the_check_that_found_it"],
    ),
    (
        "verify: connection rights on other databases are not reported",
        "app/db_admin/verify.py",
        "            if name != current:\n",
        "            if False:\n",
        [f"{VERIFY}::test_each_drift_is_reported_with_the_check_that_found_it"],
    ),
    (
        "verify: PUBLIC default execute on functions is accepted",
        "app/db_admin/verify.py",
        "    elif any(functions):\n",
        "    elif False:\n",
        [f"{VERIFY}::test_each_drift_is_reported_with_the_check_that_found_it"],
    ),
    (
        "env.py: a direct online run is allowed again",
        "alembic/env.py",
        "    if not context.is_offline_mode():\n",
        "    if False:\n",
        [f"{GRANTS}::test_a_direct_alembic_run_with_the_settings_url_is_refused"],
    ),
    (
        "bootstrap: settings a role gave itself for one database are not reset",
        "app/db_admin/bootstrap.py",
        "        run_steps(conn, database_role_setting_steps(names, configurable))",
        "        pass",
        [f"{BOOT}::test_settings_a_role_gave_itself_for_one_database_are_healed"],
    ),
    (
        "connection: the TLS parameters of the URL are dropped",
        "app/db_admin/connection.py",
        "            **tls_parameters(parts),\n",
        "",
        [UNIT_CONN],
    ),
    (
        "verify: the login probe drops the TLS parameters",
        "app/db_admin/verify.py",
        "                **tls_parameters(parts),\n            ) as probe:",
        "            ) as probe:",
        [UNIT_CONN],
    ),
    (
        "grants: any user may run them (migrator check removed)",
        "app/db_admin/grants.py",
        "        if who is None or who[0] != names.migrator:",
        "        if False:",
        [f"{GRANTS}::test_the_grants_refuse_to_run_as_anyone_but_the_migrator"],
    ),
    (
        "sql: control characters accepted in catalog names",
        "app/db_admin/sql.py",
        '        or any(c < " " for c in name)\n',
        "",
        [UNIT_SQL],
    ),
    (
        "bootstrap: roles that are members of a working role are not revoked",
        "app/db_admin/bootstrap.py",
        'f"WHERE m.rolname IN ({listed}) OR g.rolname IN ({listed}) LOOP "',
        'f"WHERE m.rolname IN ({listed}) LOOP "',
        [f"{BOOT}::test_roles_that_are_members_of_a_working_role_are_revoked"],
    ),
    (
        "connection: slow-statement logging is not silenced for the bootstrap",
        "app/db_admin/connection.py",
        '        options.append("-c log_min_duration_statement=-1")',
        "        pass",
        [UNIT_CONN],
    ),
]


def check(backend: Path) -> int:
    missing = 0
    for index, (label, rel, old, _new, _targets) in enumerate(MUTATIONS):
        text = (backend / rel).read_text(encoding="utf-8")
        found = text.count(old)
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
        text = path.read_text(encoding="utf-8")
        assert text.count(old) == 1, "the text to mutate must appear exactly once"
        path.write_text(text.replace(old, new), encoding="utf-8")
        print(" ".join(targets))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
