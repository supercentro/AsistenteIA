import logging

from app.core.config import Settings
from app.core.errors import InvalidCredentialsError
from app.core.security import PasswordService, encode_access_token
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS_MESSAGE = "Invalid email or password"


class AuthService:
    """Registration and authentication. Never logs emails, passwords, hashes or tokens."""

    def __init__(
        self, users: UserRepository, passwords: PasswordService, settings: Settings
    ) -> None:
        self._users = users
        self._passwords = passwords
        self._settings = settings

    def register_student(self, name: str, email: str, password: str) -> User:
        user = User(
            name=name,
            email=email,
            password_hash=self._passwords.hash(password),
        )  # the role is the server default `student`: the API role cannot insert it
        created = self._users.add(user)
        logger.info("user registered id=%s role=%s", created.id, created.role.value)
        return created

    def login(self, email: str, password: str) -> TokenResponse:
        user = self._users.get_by_email(email)
        if user is None:
            # Spend the same work as a real verification so timing does not reveal the account.
            self._passwords.verify_dummy(password)
            logger.info("login failed")
            raise InvalidCredentialsError(INVALID_CREDENTIALS_MESSAGE)
        if not self._passwords.verify(password, user.password_hash):
            logger.info("login failed")
            raise InvalidCredentialsError(INVALID_CREDENTIALS_MESSAGE)
        logger.info("login ok id=%s", user.id)
        return TokenResponse(
            access_token=encode_access_token(user.id, self._settings),
            expires_in=self._settings.jwt_expire_minutes * 60,
        )
