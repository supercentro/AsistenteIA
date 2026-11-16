"""Mutations of the group 8 controls (task 8.7), applied to a COPY of the code, never to the repo.

usage:
  python mutations.py check <backend dir>              every `old` text exists exactly once
  python mutations.py list                             one line per mutation: index, label
  python mutations.py apply <index> <backend copy>     edit the copy, print the test targets

A mutation is "caught" when the listed tests fail on the edited copy; the harness also runs the
same tests on the unedited copy first to prove they pass.
"""

import sys
from pathlib import Path

TEACHER = "tests/integration/test_db_roles_teacher.py"
UNIT_TEACHER = "tests/unit/test_teacher_provisioning.py"
UNIT_MATRIX = "tests/unit/test_db_privileges_matrix.py"
MIGRATION = "tests/integration/test_migrations_user_role_default.py"
UNIT_COMPOSE = "tests/unit/test_compose_database_flow.py"
M0006 = "alembic/versions/0006_users_role_server_default.py"
DEFAULT_CALL = 'op.alter_column("users", "role", server_default=sa.text("\'student\'"))'
CLI_COLUMNS = '"name", "email", "password_hash", "role", "consent_version", "consent_accepted_at"'
APP_COLUMNS = '"name", "email", "password_hash", "consent_version", "consent_accepted_at"'

# (label, file, old text, new text, pytest targets relative to the backend directory)
MUTATIONS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "matrix: the application role may insert users.role (the broad INSERT is restored)",
        "app/db_privileges.py",
        APP_COLUMNS,
        '"name", "email", "password_hash", "role", "consent_version", "consent_accepted_at"',
        [
            f"{UNIT_MATRIX}::test_mutation_granting_the_role_to_the_application_is_rejected",
            f"{TEACHER}::test_the_application_role_cannot_insert_a_teacher_or_change_a_role",
        ],
    ),
    (
        "migration 0006: the upgrade no longer sets the default",
        M0006,
        DEFAULT_CALL,
        "pass",
        [f"{MIGRATION}::test_upgrade_sets_the_default_and_keeps_every_existing_user"],
    ),
    (
        "migration 0006: the default is teacher",
        M0006,
        DEFAULT_CALL,
        DEFAULT_CALL.replace("student", "teacher"),
        [f"{MIGRATION}::test_upgrade_sets_the_default_and_keeps_every_existing_user"],
    ),
    (
        "migration 0006: the downgrade keeps the default",
        M0006,
        'op.alter_column("users", "role", server_default=None)',
        "pass",
        [f"{MIGRATION}::test_downgrade_drops_only_the_default_and_loses_no_user"],
    ),
    (
        "model: users.role loses its server default",
        "app/models/user.py",
        "        server_default=text(\"'student'\"),\n",
        "",
        [
            f"{UNIT_TEACHER}::test_the_model_declares_the_student_default_on_the_server",
            f"{MIGRATION}::test_models_and_migrations_agree_after_0006",
        ],
    ),
    (
        "registration names the role again",
        "app/services/auth_service.py",
        "            password_hash=self._passwords.hash(password),\n        )",
        "            password_hash=self._passwords.hash(password),\n"
        '            role=__import__("app.models.user", fromlist=["UserRole"]).UserRole.STUDENT,\n'
        "        )",
        [
            f"{UNIT_TEACHER}::test_registration_builds_a_user_without_naming_the_role",
            f"{TEACHER}::test_public_registration_stores_a_student_under_the_application_role",
        ],
    ),
    (
        "cli settings: the CLI falls back to the API variable DATABASE_URL",
        "app/core/config.py",
        "    cli_database_url: SecretStr\n",
        '    cli_database_url: SecretStr = Field(validation_alias="DATABASE_URL")\n',
        [
            f"{UNIT_TEACHER}::test_cli_settings_need_only_the_cli_url",
            f"{UNIT_TEACHER}::test_cli_settings_do_not_fall_back_to_the_api_url_and_do_not_leak_values",
        ],
    ),
    (
        "cli settings: an unset APP_ENV opens the seed gate",
        "app/core/config.py",
        'app_env: Literal["development", "test", "production"] = "production"\n    db_connect',
        'app_env: Literal["development", "test", "production"] = "development"\n    db_connect',
        [f"{UNIT_TEACHER}::test_the_seed_gate_fails_closed_when_app_env_is_not_provided"],
    ),
    (
        "matrix: the CLI role loses INSERT on users.role",
        "app/db_privileges.py",
        CLI_COLUMNS + "\n",
        APP_COLUMNS + "\n",
        [f"{TEACHER}::test_the_cli_role_creates_a_teacher_and_prints_no_secret"],
    ),
    (
        "matrix: the CLI role may update users",
        "app/db_privileges.py",
        CLI_COLUMNS + "\n            ),\n        ),",
        CLI_COLUMNS + '\n            ),\n            update=_cols("role"),\n        ),',
        [f"{TEACHER}::test_the_cli_role_is_limited_to_creating_and_reading_accounts"],
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
