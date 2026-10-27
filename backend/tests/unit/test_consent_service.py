import re
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings
from app.models.user import User, UserRole
from app.services.consent_service import has_current_consent
from tests.constants import TEST_JWT_SECRET

FRONTEND_CONSTANT = Path(__file__).resolve().parents[3] / "frontend/src/lib/privacyPolicy.ts"


def settings(version: str | None = None) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql+psycopg://u:p@localhost/x_test",
        "jwt_secret": TEST_JWT_SECRET,
    }
    if version:
        values["privacy_policy_version"] = version
    return Settings(**values)  # type: ignore[arg-type]


def user(version: str | None) -> User:
    return User(
        name="N",
        email="n@example.com",
        password_hash="h",
        role=UserRole.STUDENT,
        consent_version=version,
        consent_accepted_at=datetime.now(UTC) if version else None,
    )


def test_user_without_consent_has_no_current_consent() -> None:
    assert has_current_consent(user(None), settings()) is False


def test_user_with_outdated_consent_has_no_current_consent() -> None:
    assert has_current_consent(user("2025-01-v0"), settings()) is False


def test_user_with_current_consent_has_current_consent() -> None:
    assert has_current_consent(user("2026-10-v1"), settings()) is True


def test_consent_becomes_outdated_when_the_configured_version_changes() -> None:
    accepted = user("2026-10-v1")

    assert has_current_consent(accepted, settings("2027-01-v2")) is False


def ui_policy_version() -> str:
    source = FRONTEND_CONSTANT.read_text(encoding="utf-8")
    match = re.search(r"export const PRIVACY_POLICY_VERSION\s*=\s*'([^']*)'", source)
    assert match, f"PRIVACY_POLICY_VERSION constant not found in {FRONTEND_CONSTANT}"
    return match.group(1)


def test_ui_constant_equals_the_backend_default_policy_version() -> None:
    backend_default = settings().privacy_policy_version
    ui_version = ui_policy_version()

    assert ui_version == backend_default, (
        f"Privacy policy version drift: frontend constant is {ui_version!r} "
        f"but the backend default is {backend_default!r}; update both together"
    )


def test_ui_constant_is_a_valid_version_string() -> None:
    assert 1 <= len(ui_policy_version()) <= 20
