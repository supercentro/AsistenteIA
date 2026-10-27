from app.core.security import PasswordService
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository


class UserAdminService:
    """Account creation for administrative commands (never exposed over HTTP)."""

    def __init__(self, users: UserRepository, passwords: PasswordService) -> None:
        self._users = users
        self._passwords = passwords

    def exists(self, email: str) -> bool:
        return self._users.get_by_email(email) is not None

    def create_account(self, name: str, email: str, password: str, role: UserRole) -> User:
        """Create an account with an Argon2id hash; an existing email raises `ConflictError`."""
        return self._users.add(
            User(name=name, email=email, password_hash=self._passwords.hash(password), role=role)
        )
