import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import create_db_engine
from tests.constants import TEST_JWT_SECRET
from tests.integration.helpers import MakeUser, bearer, build_settings, login_token
from tests.tokens import forge_token

ME = "/api/v1/users/me"
OTHER_SECRET = "another-secret-with-enough-length-and-variety-ABC123"


def test_me_returns_only_the_callers_profile(client: TestClient, make_user: MakeUser) -> None:
    ana = make_user("ana@example.com", name="Ana")
    make_user("bob@example.com", name="Bob")

    response = client.get(ME, headers=bearer(login_token(client, ana.email)))

    body = response.json()
    assert response.status_code == 200
    assert body["id"] == ana.id
    assert body["email"] == "ana@example.com"
    assert body["role"] == "student"
    assert set(body) == {"id", "name", "email", "role", "consent_version", "consent_accepted_at"}
    assert "argon2" not in response.text


def test_me_without_authorization_header_is_401_with_challenge(client: TestClient) -> None:
    response = client.get(ME)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["code"] == "UNAUTHORIZED"


@pytest.mark.parametrize(
    "header",
    ["Basic YWJjOmRlZg==", "Bearer", "Bearer ", "bearer", "Token abc", "abc.def.ghi", ""],
)
def test_me_with_wrong_or_malformed_authorization_header_is_401(
    client: TestClient, header: str
) -> None:
    response = client.get(ME, headers={"Authorization": header})

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def _unsigned_token(user_id: str) -> str:
    def b64(data: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    now = int(datetime.now(UTC).timestamp())
    claims = {
        "sub": user_id,
        "iat": now,
        "exp": now + 3600,
        "iss": "asistenteia",
        "aud": "asistenteia-api",
    }
    return f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims)}."


def test_me_rejects_every_kind_of_invalid_token_with_the_same_generic_401(
    client: TestClient, make_user: MakeUser, clean_db: str
) -> None:
    user = make_user("ana@example.com")
    settings = build_settings(clean_db)
    good = forge_token(settings, user.id)
    head, payload, signature = good.split(".")
    tampered = f"{head}.{payload}.{('A' if signature[0] != 'A' else 'B') + signature[1:]}"
    tokens = {
        "expired": forge_token(settings, user.id, issued_minutes_ago=120, minutes_valid=60),
        "tampered": tampered,
        "wrong-secret": forge_token(settings, user.id, secret=OTHER_SECRET),
        "wrong-audience": forge_token(settings, user.id, aud="someone-else"),
        "wrong-issuer": forge_token(settings, user.id, iss="someone-else"),
        "alg-none": _unsigned_token(user.id),
        "hs384": forge_token(settings, user.id, algorithm="HS384"),
        "missing-sub": forge_token(settings, user.id, drop=("sub",)),
        "missing-iat": forge_token(settings, user.id, drop=("iat",)),
        "missing-exp": forge_token(settings, user.id, drop=("exp",)),
        "missing-iss": forge_token(settings, user.id, drop=("iss",)),
        "missing-aud": forge_token(settings, user.id, drop=("aud",)),
        "non-uuid-sub": forge_token(settings, "not-a-uuid"),
        "issued-in-future": forge_token(settings, user.id, issued_minutes_ago=-30),
        "malformed": "not.a.jwt",
    }

    bodies = set()
    for name, token in tokens.items():
        response = client.get(ME, headers=bearer(token))
        assert response.status_code == 401, name
        assert response.headers["www-authenticate"] == "Bearer", name
        assert response.json()["code"] == "UNAUTHORIZED", name
        bodies.add(response.text)
    assert len(bodies) == 1


def test_token_of_a_user_that_no_longer_exists_is_401(
    client: TestClient, make_user: MakeUser, clean_db: str
) -> None:
    user = make_user("ana@example.com")
    token = login_token(client, user.email)
    engine = create_db_engine(clean_db)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    engine.dispose()

    response = client.get(ME, headers=bearer(token))

    assert response.status_code == 401


def test_valid_signature_for_a_random_unknown_user_is_401(
    client: TestClient, clean_db: str
) -> None:
    settings = build_settings(clean_db)
    token = forge_token(settings, uuid.uuid4(), secret=TEST_JWT_SECRET)

    assert client.get(ME, headers=bearer(token)).status_code == 401


def test_token_just_before_expiry_is_still_accepted(
    client: TestClient, make_user: MakeUser, clean_db: str
) -> None:
    user = make_user("ana@example.com")
    settings = build_settings(clean_db)
    token = forge_token(settings, user.id, issued_minutes_ago=59, minutes_valid=60)

    assert client.get(ME, headers=bearer(token)).status_code == 200
    assert datetime.now(UTC) - timedelta(minutes=59) < datetime.now(UTC)
