"""Pure parts of the database administration commands (change `database-least-privilege`, 4.1-4.5).

No connection is opened here: identifier and literal quoting, the client-side SCRAM verifier, the
SQL rendered from the privilege matrix, the bootstrap plan and the redaction of secrets.
"""

import base64
import hashlib
import hmac
import re

import pytest

from app.db_admin.bootstrap import (
    application_database_steps,
    database_closing_steps,
    role_steps,
)
from app.db_admin.errors import DbAdminError
from app.db_admin.grants import grant_statements
from app.db_admin.names import (
    CONNECTION_LIMITS,
    DEFAULT_NAMES,
    EXPECTED_SEARCH_PATH,
    SEARCH_PATHS,
    RoleNames,
    RolePasswords,
)
from app.db_admin.sql import (
    VERIFIER_PATTERN,
    UnsafeIdentifierError,
    quote_ident,
    quote_literal,
    scram_verifier,
)
from app.db_privileges import APP, CLI, KNOWN_COLUMNS, MATRIX, WORKER, TableGrant

PASSWORDS = RolePasswords(
    migrator="Mig-0123456789-abcdefgh",
    app="App-0123456789-abcdefgh",
    worker="Wrk-0123456789-abcdefgh",
    cli="Cli-0123456789-abcdefgh",
)
COLUMNS = {table: sorted(columns) for table, columns in KNOWN_COLUMNS.items()}


# --- identifiers and literals ------------------------------------------------------------


@pytest.mark.parametrize("name", ["asistente_app", "a", "tstrole_x1", "_x", "a" * 63])
def test_valid_identifiers_are_quoted(name: str) -> None:
    assert quote_ident(name) == f'"{name}"'


@pytest.mark.parametrize(
    "name",
    [
        "",
        "A",
        "1a",
        "a-b",
        "a b",
        'a"b',
        "a'b",
        "a;b",
        "a--b",
        "a\nb",
        "a\x00b",
        "ñ",
        "a" * 64,
        'x"; DROP ROLE asistente; --',
        "public.users",
    ],
)
def test_unsafe_identifiers_are_refused(name: str) -> None:
    with pytest.raises(UnsafeIdentifierError):
        quote_ident(name)


def test_the_refusal_never_echoes_the_whole_value() -> None:
    with pytest.raises(UnsafeIdentifierError) as caught:
        quote_ident("x" * 5 + '"' + "SECRET-TAIL" * 5)

    assert "SECRET-TAIL" not in str(caught.value)


@pytest.mark.parametrize(
    "name",
    ["", "a\x01b", "a\tb", "a\x1bb", "a\\b", 'a"b', "x" * 64, "é" * 32],
    ids=["empty", "control-1", "tab", "escape", "backslash", "quote", "64-bytes", "multibyte-64"],
)
def test_catalog_names_that_cannot_be_quoted_safely_are_refused(name: str) -> None:
    from app.db_admin.sql import quote_catalog_name

    with pytest.raises(UnsafeIdentifierError):
        quote_catalog_name(name)


def test_catalog_names_with_ordinary_odd_characters_are_quoted() -> None:
    from app.db_admin.sql import quote_catalog_name, quote_qualified

    assert quote_catalog_name("My-DB 1") == '"My-DB 1"'
    assert quote_qualified("public", "users") == '"public"."users"'


def test_literals_double_their_quotes_and_refuse_control_characters() -> None:
    assert quote_literal("it's") == "'it''s'"
    for bad in ("a\x00b", "a\nb", "a\\b"):
        with pytest.raises(DbAdminError):
            quote_literal(bad)


# --- SCRAM verifier ----------------------------------------------------------------------


def test_the_verifier_has_the_postgresql_format_and_is_salted() -> None:
    first = scram_verifier("correct-horse-battery-1")
    second = scram_verifier("correct-horse-battery-1")

    assert re.fullmatch(VERIFIER_PATTERN, first)
    assert first.startswith("SCRAM-SHA-256$4096:")
    assert first != second  # random salt
    assert "correct-horse" not in first


def test_the_verifier_follows_rfc_5802() -> None:
    salt = b"0123456789abcdef"
    verifier = scram_verifier("pencil", salt=salt)

    _, rest = verifier.split("$", 1)
    iterations_salt, keys = rest.split("$", 1)
    iterations, salt_b64 = iterations_salt.split(":")
    salted = hashlib.pbkdf2_hmac("sha256", b"pencil", salt, int(iterations))
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored = base64.b64encode(hashlib.sha256(client_key).digest()).decode()
    server = base64.b64encode(hmac.new(salted, b"Server Key", hashlib.sha256).digest()).decode()
    assert base64.b64decode(salt_b64) == salt
    assert keys == f"{stored}:{server}"


def test_non_ascii_passwords_are_refused_rather_than_mis_hashed() -> None:
    with pytest.raises(DbAdminError):
        scram_verifier("contraseña-larga-123456")


# --- grants rendered from the matrix -----------------------------------------------------


def statements() -> list[str]:
    return grant_statements(MATRIX, DEFAULT_NAMES, COLUMNS)


def test_every_table_is_revoked_before_it_is_granted() -> None:
    for table in [*COLUMNS, "alembic_version"]:
        sql = statements()
        revoke = [
            i for i, s in enumerate(sql) if s.startswith(f'REVOKE ALL ON TABLE "public"."{table}"')
        ]
        grant = [i for i, s in enumerate(sql) if s.startswith("GRANT") and f'"{table}"' in s]
        assert revoke, table
        assert not grant or max(revoke) < min(grant), table


def test_every_table_is_named_with_its_schema_because_sessions_search_only_the_catalog() -> None:
    for sql in statements():
        assert '"public".' in sql, sql
        assert ' ON TABLE "' not in sql.replace(' ON TABLE "public"."', ""), sql


def test_public_and_unlisted_roles_lose_everything_first() -> None:
    sql = statements()

    assert 'REVOKE ALL ON TABLE "public"."users" FROM PUBLIC' in sql
    assert 'REVOKE ALL ON TABLE "public"."alembic_version" FROM PUBLIC' in sql
    for role in (DEFAULT_NAMES.app, DEFAULT_NAMES.worker, DEFAULT_NAMES.cli):
        assert f'REVOKE ALL ON TABLE "public"."alembic_version" FROM "{role}"' in sql
        assert not [s for s in sql if s.startswith("GRANT") and "alembic_version" in s]


def test_full_column_sets_become_table_level_and_partial_ones_stay_column_level() -> None:
    sql = statements()
    app = f'"{DEFAULT_NAMES.app}"'

    assert f'GRANT SELECT ON TABLE "public"."users" TO {app}' in sql
    assert (
        f'GRANT INSERT ("email", "name", "password_hash") ON TABLE "public"."users" TO {app}'  # noqa: E501
        in sql
    )
    assert (
        f'GRANT UPDATE ("consent_accepted_at", "consent_version") ON TABLE "public"."users" TO {app}'  # noqa: E501
        in sql
    )
    assert (
        f'GRANT SELECT ("id") ON TABLE "public"."document_chunks" TO "{DEFAULT_NAMES.worker}"'
        in sql
    )
    assert f'GRANT DELETE ON TABLE "public"."subjects" TO {app}' in sql


def test_nothing_is_granted_beyond_the_matrix() -> None:
    sql = statements()

    # The fencing token is never readable or changeable by the application role; it can only be
    # sent as NULL by the ORM insert of a job (proved in group 5).
    reads = [s for s in sql if "locked_by" in s and DEFAULT_NAMES.app in s]
    assert all(s.startswith("GRANT INSERT") for s in reads)
    assert not [s for s in sql if s.startswith("GRANT") and "ALL" in s.split(" ON ")[0]]
    assert not [s for s in sql if "WITH GRANT OPTION" in s]
    assert not [s for s in sql if s.startswith("GRANT") and "PUBLIC" in s]
    cli = f'"{DEFAULT_NAMES.cli}"'
    assert [s for s in sql if s.startswith("GRANT") and s.endswith(f"TO {cli}")] == [
        f'GRANT SELECT ON TABLE "public"."users" TO {cli}',
        f'GRANT INSERT ("email", "name", "password_hash", "role") ON TABLE "public"."users" TO {cli}',  # noqa: E501
    ]


def test_a_matrix_with_an_unknown_column_is_refused() -> None:
    broken = {APP: {"users": TableGrant(select=frozenset({"no_such_column"}))}}

    with pytest.raises(DbAdminError):
        grant_statements(broken, DEFAULT_NAMES, COLUMNS)


def test_a_table_missing_from_the_catalog_is_refused() -> None:
    with pytest.raises(DbAdminError):
        grant_statements(MATRIX, DEFAULT_NAMES, {"users": COLUMNS["users"]})


def test_unsafe_role_names_never_reach_a_statement() -> None:
    evil = RoleNames(migrator="m", app='a"; DROP ROLE x; --', worker="w", cli="c")

    with pytest.raises(UnsafeIdentifierError):
        grant_statements(MATRIX, evil, COLUMNS)


def test_the_rendering_is_deterministic() -> None:
    assert statements() == statements()
    assert len(statements()) == len(set(statements()))


# --- bootstrap plan ----------------------------------------------------------------------


def verifiers() -> dict[str, str]:
    return {
        role: scram_verifier(getattr(PASSWORDS, role))
        for role in ("migrator", "app", "worker", "cli")
    }


def test_missing_roles_are_created_with_every_restricting_attribute() -> None:
    steps = role_steps(DEFAULT_NAMES, verifiers(), existing=set())
    creates = [s for s in steps if s.sql.startswith("CREATE ROLE")]

    assert len(creates) == 4
    for step in creates:
        for attribute in (
            "LOGIN",
            "NOSUPERUSER",
            "NOCREATEDB",
            "NOCREATEROLE",
            "NOREPLICATION",
            "NOBYPASSRLS",
        ):
            assert attribute in step.sql
        assert "INHERIT" in step.sql and "CONNECTION LIMIT" in step.sql


def test_existing_roles_are_altered_not_created() -> None:
    steps = role_steps(DEFAULT_NAMES, verifiers(), existing=set(DEFAULT_NAMES.all()))

    assert not [s for s in steps if s.sql.startswith("CREATE ROLE")]
    alters = [s for s in steps if s.sql.startswith("ALTER ROLE") and "NOSUPERUSER" in s.sql]
    assert len(alters) == 4


def test_connection_limits_come_from_the_table() -> None:
    steps = role_steps(DEFAULT_NAMES, verifiers(), existing=set())
    for logical, limit in CONNECTION_LIMITS.items():
        role = getattr(DEFAULT_NAMES, logical)
        step = next(s for s in steps if s.sql.startswith("CREATE ROLE") and f'"{role}"' in s.sql)
        assert f"CONNECTION LIMIT {limit}" in step.sql


def test_settings_are_reset_before_the_intended_ones_are_set() -> None:
    steps = role_steps(DEFAULT_NAMES, verifiers(), existing=set(DEFAULT_NAMES.all()))
    for logical in ("migrator", "app", "worker", "cli"):
        role = getattr(DEFAULT_NAMES, logical)
        reset = next(i for i, s in enumerate(steps) if s.sql == f'ALTER ROLE "{role}" RESET ALL')
        setting = next(
            i
            for i, s in enumerate(steps)
            if s.sql == f'ALTER ROLE "{role}" SET search_path = {SEARCH_PATHS[logical]}'
        )
        assert reset < setting


def test_the_migrator_keeps_public_and_the_runtime_roles_list_the_catalog_first() -> None:
    assert SEARCH_PATHS["migrator"] == "public"
    for logical in ("app", "worker", "cli"):
        assert SEARCH_PATHS[logical] == EXPECTED_SEARCH_PATH == "pg_catalog, public"


def test_memberships_are_revoked() -> None:
    steps = role_steps(DEFAULT_NAMES, verifiers(), existing=set(DEFAULT_NAMES.all()))

    assert any("pg_auth_members" in s.sql for s in steps)  # the revoke is driven by the catalog


def test_only_the_steps_that_carry_a_verifier_are_sensitive_and_they_are_masked() -> None:
    steps = role_steps(DEFAULT_NAMES, verifiers(), existing=set())
    sensitive = [s for s in steps if s.sensitive]

    assert sensitive and all("SCRAM-SHA-256$" in s.sql for s in sensitive)
    assert not [s for s in steps if not s.sensitive and "SCRAM-SHA-256" in s.sql]
    for step in sensitive:
        assert "SCRAM" not in repr(step) and "SCRAM" not in step.display()


def test_no_clear_text_password_appears_in_any_step() -> None:
    steps = role_steps(DEFAULT_NAMES, verifiers(), existing=set(DEFAULT_NAMES.all()))
    text = "\n".join(s.sql + repr(s) + s.display() for s in steps)

    for password in (PASSWORDS.migrator, PASSWORDS.app, PASSWORDS.worker, PASSWORDS.cli):
        assert password not in text


def test_every_other_database_is_closed_to_public_including_templates() -> None:
    steps = database_closing_steps(["asistenteia", "postgres", "template0", "template1", "other"])
    sql = [s.sql for s in steps]

    assert 'REVOKE ALL ON DATABASE "template1" FROM PUBLIC' in sql
    assert 'REVOKE ALL ON DATABASE "template0" FROM PUBLIC' in sql
    assert 'REVOKE ALL ON DATABASE "postgres" FROM PUBLIC' in sql
    assert 'REVOKE ALL ON DATABASE "other" FROM PUBLIC' in sql


def test_a_database_name_that_is_not_an_identifier_is_refused_not_quoted_blindly() -> None:
    with pytest.raises(UnsafeIdentifierError):
        database_closing_steps(['bad"name'])


def test_the_application_database_steps() -> None:
    steps = application_database_steps(DEFAULT_NAMES, "asistenteia")
    sql = [s.sql for s in steps]

    assert 'REVOKE ALL ON DATABASE "asistenteia" FROM PUBLIC' in sql
    for role in DEFAULT_NAMES.all():
        assert f'GRANT CONNECT ON DATABASE "asistenteia" TO "{role}"' in sql
    assert 'REVOKE ALL ON SCHEMA "public" FROM PUBLIC' in sql
    assert f'GRANT CREATE, USAGE ON SCHEMA "public" TO "{DEFAULT_NAMES.migrator}"' in sql
    for role in (DEFAULT_NAMES.app, DEFAULT_NAMES.worker, DEFAULT_NAMES.cli):
        assert f'GRANT USAGE ON SCHEMA "public" TO "{role}"' in sql
        assert f'REVOKE CREATE ON SCHEMA "public" FROM "{role}"' in sql
    assert "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public" in sql
    default = f'ALTER DEFAULT PRIVILEGES FOR ROLE "{DEFAULT_NAMES.migrator}" REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC'  # noqa: E501
    assert default in sql
    assert not [s for s in sql if "IN SCHEMA" in s]  # the per-schema form has no effect (A-05)


def test_the_grants_of_the_logical_roles_match_the_physical_names() -> None:
    assert DEFAULT_NAMES.for_logical(APP) == "asistente_app"
    assert DEFAULT_NAMES.for_logical(WORKER) == "asistente_worker"
    assert DEFAULT_NAMES.for_logical(CLI) == "asistente_cli"
    assert RoleNames.with_prefix("tstrole_").app == "tstrole_app"


def test_role_passwords_are_never_printed() -> None:
    assert "0123456789" not in repr(PASSWORDS) and "0123456789" not in str(PASSWORDS)
