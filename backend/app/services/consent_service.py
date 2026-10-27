import logging
from datetime import UTC, datetime

from app.core.config import Settings
from app.core.errors import InvalidConsentVersionError
from app.models.user import User

logger = logging.getLogger(__name__)


class ConsentService:
    """Records acceptance of the currently configured privacy-policy version."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def record(self, user: User, version: str) -> User:
        current = self._settings.privacy_policy_version
        if version != current:
            raise InvalidConsentVersionError(
                "The privacy policy version is not the current one",
                details={"current_version": current},
            )
        user.consent_version = version
        user.consent_accepted_at = datetime.now(UTC)
        logger.info("consent recorded id=%s version=%s", user.id, version)
        return user


def has_current_consent(user: User, settings: Settings) -> bool:
    """True only when the stored consent is for the version currently configured.

    Used by the chat change to gate usage; not enforced by any endpoint of this change.
    """
    return user.consent_version == settings.privacy_policy_version
