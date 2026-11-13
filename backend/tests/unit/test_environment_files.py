"""Each environment file holds the secrets of one consumer (change `database-least-privilege`).

Task 3.1 and 3.3. The files are read as text; nothing is started. The Compose file is not changed
by this group (group 6 wires the new files to their services), so these tests cover the examples,
the Git rules and the rule that no secret lives in two files with different owners.
"""

from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests.db_support import BACKEND_DIR
from tests.unit.test_deployment_files import REPO, example_assignments, git_ignores

EXAMPLES = {
    "api": BACKEND_DIR / ".env.example",
    "worker": BACKEND_DIR / ".env.worker.example",
    "db": BACKEND_DIR / ".env.db.example",
    "migrate": BACKEND_DIR / ".env.migrate.example",
    "roles": BACKEND_DIR / ".env.roles.example",
    "cli": BACKEND_DIR / ".env.cli.example",
    "test": BACKEND_DIR / ".env.test.example",
}
ROLE_PASSWORDS = {
    "DB_MIGRATOR_PASSWORD",
    "DB_APP_PASSWORD",
    "DB_WORKER_PASSWORD",
    "DB_CLI_PASSWORD",
}
# Variable -> the only example file that may declare it.
SINGLE_OWNER = {
    "JWT_SECRET": "api",
    "POSTGRES_USER": "db",
    "POSTGRES_PASSWORD": "db",
    "POSTGRES_DB": "db",
    "MIGRATION_DATABASE_URL": "migrate",
    "ADMIN_DATABASE_URL": "roles",
    "CLI_DATABASE_URL": "cli",
    **dict.fromkeys(ROLE_PASSWORDS, "roles"),
    "TEST_DATABASE_URL": "test",
    "TEST_ADMIN_DATABASE_URL": "test",
}


def declared(kind: str) -> dict[str, tuple[bool, str]]:
    return example_assignments(EXAMPLES[kind])


@pytest.mark.parametrize("kind", EXAMPLES)
def test_every_example_exists(kind: str) -> None:
    assert EXAMPLES[kind].is_file(), EXAMPLES[kind].name


@pytest.mark.parametrize(("variable", "owner"), sorted(SINGLE_OWNER.items()))
def test_each_secret_variable_is_declared_in_exactly_one_example(variable: str, owner: str) -> None:
    holders = {kind for kind in EXAMPLES if variable in declared(kind)}

    assert holders == {owner}, variable


def test_the_api_example_receives_no_database_administration_or_test_variable() -> None:
    names = set(declared("api"))

    for forbidden in (
        "POSTGRES_",
        "TEST_",
        "MIGRATION_",
        "ADMIN_",
        "DB_MIGRATOR",
        "DB_CLI",
        "CLI_",
    ):
        assert not [n for n in names if n.startswith(forbidden)], forbidden
    assert not names & ROLE_PASSWORDS


def test_the_worker_example_receives_none_of_the_new_variables() -> None:
    names = set(declared("worker"))

    assert not names & set(SINGLE_OWNER) and "DATABASE_URL" in names


def test_the_migrate_example_holds_exactly_the_migrator_url() -> None:
    assert set(declared("migrate")) == {"MIGRATION_DATABASE_URL"}


def test_the_cli_example_holds_exactly_the_cli_url_for_the_cli_role() -> None:
    assert set(declared("cli")) == {"CLI_DATABASE_URL"}
    parts = urlsplit(declared("cli")["CLI_DATABASE_URL"][1])

    assert parts.username == "asistente_cli" and parts.hostname == "db"
    assert parts.path == "/" + declared("db")["POSTGRES_DB"][1]


def test_the_roles_example_holds_exactly_the_administrator_url_and_the_four_passwords() -> None:
    assert set(declared("roles")) == {"ADMIN_DATABASE_URL", *ROLE_PASSWORDS}


def test_the_test_example_holds_exactly_the_two_host_only_urls() -> None:
    assert set(declared("test")) == {"TEST_DATABASE_URL", "TEST_ADMIN_DATABASE_URL"}


@pytest.mark.parametrize("kind", ["migrate", "roles", "cli", "test"])
def test_the_new_examples_hold_only_placeholders(kind: str) -> None:
    for name, (active, raw) in declared(kind).items():
        assert active, name
        assert "CHANGE_ME" in raw, name


def test_the_migrator_url_example_names_the_migrator_and_the_application_database() -> None:
    parts = urlsplit(declared("migrate")["MIGRATION_DATABASE_URL"][1])
    database = declared("db")["POSTGRES_DB"][1]

    assert parts.username == "asistente_migrator"
    assert parts.hostname == "db" and parts.path == "/" + database


def test_the_administrator_url_example_matches_the_database_server_example() -> None:
    parts = urlsplit(declared("roles")["ADMIN_DATABASE_URL"][1])

    assert parts.username == declared("db")["POSTGRES_USER"][1]
    assert parts.hostname == "db" and parts.path == "/postgres"


def test_the_test_examples_use_a_test_database_on_the_loopback_of_the_host() -> None:
    test = urlsplit(declared("test")["TEST_DATABASE_URL"][1])
    admin = urlsplit(declared("test")["TEST_ADMIN_DATABASE_URL"][1])

    assert test.path.endswith("_test")
    assert test.hostname == admin.hostname == "127.0.0.1" and test.port == admin.port


def test_the_test_example_database_differs_from_the_application_database() -> None:
    api = urlsplit(declared("api")["DATABASE_URL"][1])
    test = urlsplit(declared("test")["TEST_DATABASE_URL"][1])

    assert api.path != test.path


@pytest.mark.parametrize("kind", ["migrate", "roles", "cli", "test"])
def test_the_new_real_files_are_ignored_and_the_examples_are_not(kind: str) -> None:
    real = f"backend/{EXAMPLES[kind].name.removesuffix('.example')}"
    verdicts = (git_ignores(real), git_ignores(f"backend/{EXAMPLES[kind].name}"))
    if None in verdicts:
        pytest.skip("git or the repository metadata is not available")

    assert verdicts == (True, False)


def test_no_new_real_file_is_tracked_and_no_image_can_contain_one() -> None:
    dockerignore = (BACKEND_DIR / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert ".env.*" in dockerignore  # covers .env.migrate, .env.roles and .env.test
    for name in (".env.migrate", ".env.roles", ".env.test"):
        assert not (REPO / "backend" / name).is_relative_to(REPO / "frontend")
    assert Path(REPO / ".gitignore").read_text(encoding="utf-8").count(".env.*") >= 1
