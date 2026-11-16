"""The consent is stored before the 200, and a refused write is an error (group 7, task 7.1).

The API runs under the real application role on a database built the way the design says
(bootstrap, migration, grants) in a disposable cluster. The defect reproduced here (finding N-1 of
the spike): when PostgreSQL refused the `UPDATE`, the request had already been answered with 200
because the commit happened after the response, and nothing was stored.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.db_admin.grants import apply_grants
from tests.db_admin_support import Cluster
from tests.db_admin_support import cluster as cluster  # noqa: F401  (fixture)
from tests.db_admin_support import scratch_database as scratch_database  # noqa: F401  (fixture)
from tests.db_roles_support import own_database as own_database
from tests.integration.helpers import (
    DEFAULT_PASSWORD,
    bearer,
    build_app,
    insert_user,
    login_token,
)

CONSENT = "/api/v1/users/me/consent"
CURRENT = "2026-10-v1"
CONSENT_COLUMNS = "(consent_version, consent_accepted_at)"


@contextmanager
def api_client(cluster: Cluster, database: str) -> Iterator[TestClient]:
    app = build_app(cluster.role_url("app", database))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def stored(cluster: Cluster, database: str, email: str) -> tuple[str | None, object]:
    """What a separate session sees, with the administrator."""
    with cluster.admin_connection(database) as conn:
        row = conn.execute(
            "SELECT consent_version, consent_accepted_at FROM users WHERE email = %s", (email,)
        ).fetchone()
    assert row is not None
    return row[0], row[1]


def student(cluster: Cluster, database: str, email: str = "ana@example.com") -> str:
    insert_user(cluster.admin(database), email)
    return email


def test_the_consent_is_visible_from_another_session_after_the_200(
    cluster: Cluster, own_database: str
) -> None:
    email = student(cluster, own_database)
    with api_client(cluster, own_database) as client:
        headers = bearer(login_token(client, email))

        response = client.post(CONSENT, json={"consent_version": CURRENT}, headers=headers)

        assert response.status_code == 200
        version, accepted_at = stored(cluster, own_database, email)
        assert version == CURRENT and accepted_at is not None
        assert response.json()["consent_version"] == CURRENT


def test_accepting_twice_is_idempotent(cluster: Cluster, own_database: str) -> None:
    email = student(cluster, own_database)
    with api_client(cluster, own_database) as client:
        headers = bearer(login_token(client, email))
        first = client.post(CONSENT, json={"consent_version": CURRENT}, headers=headers)
        _, first_time = stored(cluster, own_database, email)

        second = client.post(CONSENT, json={"consent_version": CURRENT}, headers=headers)

    assert first.status_code == second.status_code == 200
    version, second_time = stored(cluster, own_database, email)
    assert version == CURRENT and second_time >= first_time  # type: ignore[operator]


def test_a_refused_update_is_an_error_and_stores_nothing(
    cluster: Cluster,
    own_database: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    email = student(cluster, own_database)
    caplog.set_level(logging.DEBUG)
    with cluster.admin_connection(own_database) as conn:  # the defect of the spike: no UPDATE right
        conn.execute(
            f'REVOKE UPDATE {CONSENT_COLUMNS} ON TABLE "public"."users" FROM "{cluster.names.app}"'
        )
    with api_client(cluster, own_database) as client:
        headers = bearer(login_token(client, email))

        response = client.post(CONSENT, json={"consent_version": CURRENT}, headers=headers)

    assert response.status_code == 500  # never a 200 without stored evidence
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert stored(cluster, own_database, email) == (None, None)  # no partial change either
    leaked = response.text + caplog.text
    for secret in (email, DEFAULT_PASSWORD, "password_hash", make_url(cluster.admin_url).password):
        assert secret and secret not in leaked


def test_the_service_recovers_when_the_privilege_returns(
    cluster: Cluster, own_database: str
) -> None:
    email = student(cluster, own_database)
    with cluster.admin_connection(own_database) as conn:
        conn.execute(
            f'REVOKE UPDATE {CONSENT_COLUMNS} ON TABLE "public"."users" FROM "{cluster.names.app}"'
        )
    with api_client(cluster, own_database) as client:
        headers = bearer(login_token(client, email))
        assert (
            client.post(CONSENT, json={"consent_version": CURRENT}, headers=headers).status_code
            == 500
        )
        assert stored(cluster, own_database, email) == (None, None)

        apply_grants(cluster.migrator_url(own_database), names=cluster.names)  # the matrix again
        again = client.post(CONSENT, json={"consent_version": CURRENT}, headers=headers)

        assert again.status_code == 200  # the failed request left no broken session behind
        assert stored(cluster, own_database, email)[0] == CURRENT


def test_a_wrong_version_is_a_422_and_stores_nothing(cluster: Cluster, own_database: str) -> None:
    email = student(cluster, own_database)
    with api_client(cluster, own_database) as client:
        headers = bearer(login_token(client, email))

        response = client.post(CONSENT, json={"consent_version": "1999-01-v0"}, headers=headers)

    assert response.status_code == 422
    assert stored(cluster, own_database, email) == (None, None)
