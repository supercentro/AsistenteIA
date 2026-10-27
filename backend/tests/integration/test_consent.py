import time
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import create_db_engine
from app.models.user import UserRole
from tests.integration.helpers import MakeUser, bearer, build_app, login_token

CONSENT = "/api/v1/users/me/consent"
CURRENT = "2026-10-v1"


def stored_consent(database_url: str, user_id: str) -> tuple[str | None, datetime | None]:
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT consent_version, consent_accepted_at FROM users WHERE id = :id"),
                {"id": user_id},
            ).one()
        return row[0], row[1]
    finally:
        engine.dispose()


def test_current_version_is_recorded_with_server_time(
    client: TestClient, make_user: MakeUser, clean_db: str
) -> None:
    user = make_user("ana@example.com")
    token = login_token(client, user.email)

    response = client.post(CONSENT, json={"consent_version": CURRENT}, headers=bearer(token))

    body = response.json()
    assert response.status_code == 200
    assert body["consent_version"] == CURRENT
    assert body["consent_accepted_at"] is not None
    assert body["id"] == user.id
    version, accepted_at = stored_consent(clean_db, user.id)
    assert version == CURRENT
    assert accepted_at is not None


def test_a_teacher_may_also_record_consent(client: TestClient, make_user: MakeUser) -> None:
    teacher = make_user("teacher@example.com", UserRole.TEACHER)
    token = login_token(client, teacher.email)

    response = client.post(CONSENT, json={"consent_version": CURRENT}, headers=bearer(token))

    assert response.status_code == 200


def test_profile_shows_the_recorded_consent(client: TestClient, make_user: MakeUser) -> None:
    user = make_user("ana@example.com")
    headers = bearer(login_token(client, user.email))
    client.post(CONSENT, json={"consent_version": CURRENT}, headers=headers)

    me = client.get("/api/v1/users/me", headers=headers).json()

    assert me["consent_version"] == CURRENT
    assert me["consent_accepted_at"] is not None


def test_other_version_is_rejected_with_current_version_and_nothing_changes(
    client: TestClient, make_user: MakeUser, clean_db: str
) -> None:
    user = make_user("ana@example.com")
    headers = bearer(login_token(client, user.email))

    for version in ("2025-01-v0", "2099-12-v9", CURRENT.upper(), f" {CURRENT}"):
        response = client.post(CONSENT, json={"consent_version": version}, headers=headers)

        assert response.status_code == 422, version
        body = response.json()
        assert body["code"] == "INVALID_CONSENT_VERSION"
        assert body["details"] == {"current_version": CURRENT}
    assert stored_consent(clean_db, user.id) == (None, None)


def test_outdated_version_does_not_overwrite_an_existing_consent(
    client: TestClient, make_user: MakeUser, clean_db: str
) -> None:
    user = make_user("ana@example.com")
    headers = bearer(login_token(client, user.email))
    client.post(CONSENT, json={"consent_version": CURRENT}, headers=headers)
    before = stored_consent(clean_db, user.id)

    client.post(CONSENT, json={"consent_version": "old"}, headers=headers)

    assert stored_consent(clean_db, user.id) == before


def test_empty_or_overlong_version_is_a_validation_error(
    client: TestClient, make_user: MakeUser, clean_db: str
) -> None:
    user = make_user("ana@example.com")
    headers = bearer(login_token(client, user.email))

    for version in ("", "v" * 21):
        response = client.post(CONSENT, json={"consent_version": version}, headers=headers)

        assert response.status_code == 422
        assert response.json()["code"] == "VALIDATION_ERROR"
    assert client.post(CONSENT, json={}, headers=headers).status_code == 422
    assert stored_consent(clean_db, user.id) == (None, None)


def test_reacceptance_updates_the_timestamp_and_version(
    client: TestClient, make_user: MakeUser, clean_db: str
) -> None:
    user = make_user("ana@example.com")
    headers = bearer(login_token(client, user.email))
    client.post(CONSENT, json={"consent_version": CURRENT}, headers=headers)
    _, first = stored_consent(clean_db, user.id)
    time.sleep(0.02)

    response = client.post(CONSENT, json={"consent_version": CURRENT}, headers=headers)

    _, second = stored_consent(clean_db, user.id)
    assert response.status_code == 200
    assert first is not None
    assert second is not None
    assert second > first


def test_changing_the_configured_version_requires_accepting_the_new_one(
    client: TestClient, make_user: MakeUser, clean_db: str
) -> None:
    user = make_user("ana@example.com")
    headers = bearer(login_token(client, user.email))
    client.post(CONSENT, json={"consent_version": CURRENT}, headers=headers)

    with TestClient(build_app(clean_db, privacy_policy_version="2027-01-v2")) as upgraded:
        rejected = upgraded.post(CONSENT, json={"consent_version": CURRENT}, headers=headers)
        accepted = upgraded.post(CONSENT, json={"consent_version": "2027-01-v2"}, headers=headers)

    assert rejected.status_code == 422
    assert rejected.json()["details"] == {"current_version": "2027-01-v2"}
    assert accepted.status_code == 200
    assert stored_consent(clean_db, user.id)[0] == "2027-01-v2"


def test_consent_requires_authentication(client: TestClient) -> None:
    for headers in ({}, {"Authorization": "Bearer not.a.jwt"}):
        response = client.post(CONSENT, json={"consent_version": CURRENT}, headers=headers)

        assert response.status_code == 401


def test_consent_of_one_user_does_not_touch_another(
    client: TestClient, make_user: MakeUser, clean_db: str
) -> None:
    ana = make_user("ana@example.com")
    bob = make_user("bob@example.com")

    client.post(
        CONSENT,
        json={"consent_version": CURRENT},
        headers=bearer(login_token(client, ana.email)),
    )

    assert stored_consent(clean_db, ana.id)[0] == CURRENT
    assert stored_consent(clean_db, bob.id) == (None, None)
