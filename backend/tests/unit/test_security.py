import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest

from app.core.config import Settings
from app.core.errors import UnauthorizedError
from app.core.security import (
    PasswordService,
    decode_access_token,
    encode_access_token,
)
from tests.constants import TEST_JWT_SECRET

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
USER_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://u:p@localhost/x_test",
        jwt_secret=TEST_JWT_SECRET,
    )


def forge(settings: Settings, secret: str | None = None, **overrides: Any) -> str:
    """Build a token by hand so tests can break individual claims."""
    claims: dict[str, Any] = {
        "sub": str(USER_ID),
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(minutes=60)).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, secret or TEST_JWT_SECRET, algorithm="HS256")


# ---------------------------------------------------------------- passwords


def test_hash_is_argon2id_and_differs_from_password() -> None:
    service = PasswordService(time_cost=1, memory_cost=8, parallelism=1)

    hashed = service.hash("correct horse battery")

    assert hashed.startswith("$argon2id$")
    assert "correct horse battery" not in hashed


def test_verify_accepts_right_and_rejects_wrong_password() -> None:
    service = PasswordService(time_cost=1, memory_cost=8, parallelism=1)
    hashed = service.hash("correct horse battery")

    assert service.verify("correct horse battery", hashed) is True
    assert service.verify("wrong password!!", hashed) is False


def test_verify_returns_false_for_garbage_hash_without_raising() -> None:
    service = PasswordService(time_cost=1, memory_cost=8, parallelism=1)

    assert service.verify("whatever-password", "not-a-hash") is False


def test_dummy_verification_always_fails_and_never_raises() -> None:
    service = PasswordService(time_cost=1, memory_cost=8, parallelism=1)

    assert service.verify_dummy("anything-at-all") is False


def test_same_password_produces_different_hashes() -> None:
    service = PasswordService(time_cost=1, memory_cost=8, parallelism=1)

    assert service.hash("repeatable-pass") != service.hash("repeatable-pass")


def test_default_service_uses_library_defaults_for_argon2id() -> None:
    service = PasswordService()

    assert service.hash("production-grade-pass").startswith("$argon2id$")


# ------------------------------------------------------------------ tokens


def test_encoded_token_has_exactly_the_required_claims_and_hs256(settings: Settings) -> None:
    token = encode_access_token(USER_ID, settings, now=NOW)

    header = jwt.get_unverified_header(token)
    claims = jwt.decode(token, options={"verify_signature": False})
    assert header["alg"] == "HS256"
    assert set(claims) == {"sub", "iat", "exp", "iss", "aud"}
    assert claims["sub"] == str(USER_ID)
    assert claims["exp"] - claims["iat"] == settings.jwt_expire_minutes * 60
    assert claims["iss"] == settings.jwt_issuer
    assert claims["aud"] == settings.jwt_audience


def test_decode_returns_user_id_for_valid_token(settings: Settings) -> None:
    token = encode_access_token(USER_ID, settings, now=NOW)

    assert decode_access_token(token, settings, now=NOW + timedelta(minutes=1)) == USER_ID


def test_decode_rejects_expired_token(settings: Settings) -> None:
    token = encode_access_token(USER_ID, settings, now=NOW)

    with pytest.raises(UnauthorizedError):
        decode_access_token(token, settings, now=NOW + timedelta(minutes=61))


def test_decode_accepts_token_one_second_before_expiry(settings: Settings) -> None:
    token = encode_access_token(USER_ID, settings, now=NOW)

    decode_access_token(token, settings, now=NOW + timedelta(minutes=60) - timedelta(seconds=1))


def test_decode_rejects_token_issued_in_the_future(settings: Settings) -> None:
    token = encode_access_token(USER_ID, settings, now=NOW + timedelta(hours=1))

    with pytest.raises(UnauthorizedError):
        decode_access_token(token, settings, now=NOW)


def test_decode_rejects_tampered_signature(settings: Settings) -> None:
    token = encode_access_token(USER_ID, settings, now=NOW)
    head, payload, signature = token.split(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]

    with pytest.raises(UnauthorizedError):
        decode_access_token(f"{head}.{payload}.{flipped}", settings, now=NOW)


def test_decode_rejects_payload_swapped_with_original_signature(settings: Settings) -> None:
    token = encode_access_token(USER_ID, settings, now=NOW)
    other = encode_access_token(uuid.uuid4(), settings, now=NOW)
    head, _, signature = token.split(".")
    other_payload = other.split(".")[1]

    with pytest.raises(UnauthorizedError):
        decode_access_token(f"{head}.{other_payload}.{signature}", settings, now=NOW)


def test_decode_rejects_token_signed_with_another_secret(settings: Settings) -> None:
    token = forge(settings, secret="another-secret-of-sufficient-length-1234567890")

    with pytest.raises(UnauthorizedError):
        decode_access_token(token, settings, now=NOW)


@pytest.mark.parametrize(
    "overrides",
    [{"aud": "someone-else"}, {"iss": "someone-else"}],
    ids=["audience", "issuer"],
)
def test_decode_rejects_wrong_audience_or_issuer(
    settings: Settings, overrides: dict[str, Any]
) -> None:
    with pytest.raises(UnauthorizedError):
        decode_access_token(forge(settings, **overrides), settings, now=NOW)


def test_decode_rejects_alg_none(settings: Settings) -> None:
    def b64(data: dict[str, Any]) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    claims = {
        "sub": str(USER_ID),
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(hours=1)).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    unsigned = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims)}."

    with pytest.raises(UnauthorizedError):
        decode_access_token(unsigned, settings, now=NOW)


def test_decode_rejects_other_hmac_algorithms(settings: Settings) -> None:
    claims = {
        "sub": str(USER_ID),
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(hours=1)).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    token = jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS384")

    with pytest.raises(UnauthorizedError):
        decode_access_token(token, settings, now=NOW)


@pytest.mark.parametrize("missing", ["sub", "iat", "exp", "iss", "aud"])
def test_decode_rejects_token_missing_a_required_claim(settings: Settings, missing: str) -> None:
    claims = {
        "sub": str(USER_ID),
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(hours=1)).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    del claims[missing]
    token = jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")

    with pytest.raises(UnauthorizedError):
        decode_access_token(token, settings, now=NOW)


@pytest.mark.parametrize("sub", ["not-a-uuid", "", "12345"])
def test_decode_rejects_non_uuid_subject(settings: Settings, sub: str) -> None:
    with pytest.raises(UnauthorizedError):
        decode_access_token(forge(settings, sub=sub), settings, now=NOW)


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c", "a.b", "....", "Bearer x"])
def test_decode_rejects_malformed_tokens(settings: Settings, token: str) -> None:
    with pytest.raises(UnauthorizedError):
        decode_access_token(token, settings, now=NOW)


def test_decode_ignores_extra_role_claim(settings: Settings) -> None:
    token = forge(settings, role="teacher")

    assert decode_access_token(token, settings, now=NOW) == USER_ID


def test_all_rejections_share_the_same_generic_message(settings: Settings) -> None:
    messages = set()
    for token in ("garbage", forge(settings, aud="x"), forge(settings, sub="nope")):
        with pytest.raises(UnauthorizedError) as exc:
            decode_access_token(token, settings, now=NOW)
        messages.add(exc.value.message)

    assert len(messages) == 1


# ------------------------------------------------------ strictness (review)


def test_decode_rejects_audience_given_as_a_list(settings: Settings) -> None:
    token = forge(settings, aud=[settings.jwt_audience, "another-service"])

    with pytest.raises(UnauthorizedError):
        decode_access_token(token, settings, now=NOW)


LETTERED_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def test_decode_accepts_the_canonical_form_of_the_same_subject(settings: Settings) -> None:
    assert decode_access_token(forge(settings, sub=str(LETTERED_ID)), settings, now=NOW) == (
        LETTERED_ID
    )


@pytest.mark.parametrize(
    "sub",
    [
        str(LETTERED_ID).upper(),
        LETTERED_ID.hex,
        f"{{{LETTERED_ID}}}",
        f"urn:uuid:{LETTERED_ID}",
    ],
    ids=["uppercase", "no-hyphens", "braces", "urn"],
)
def test_decode_rejects_non_canonical_uuid_subjects(settings: Settings, sub: str) -> None:
    with pytest.raises(UnauthorizedError):
        decode_access_token(forge(settings, sub=sub), settings, now=NOW)


@pytest.mark.parametrize("claim", ["exp", "iat"])
@pytest.mark.parametrize("bad", [True, "1790000000"], ids=["bool", "string"])
def test_decode_rejects_non_numeric_time_claims(
    settings: Settings, claim: str, bad: object
) -> None:
    overrides: dict[str, Any] = {claim: bad}

    with pytest.raises(UnauthorizedError):
        decode_access_token(forge(settings, **overrides), settings, now=NOW)
