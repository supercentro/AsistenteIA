"""Shared FastAPI dependencies."""

import logging
from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.rate_limit import RateLimiter
from app.core.security import TOKEN_ERROR_MESSAGE, PasswordService, decode_access_token
from app.models.user import User, UserRole
from app.rag.embedder import Embedder
from app.repositories.activity_repository import ActivityRepository
from app.repositories.enrollment_repository import EnrollmentRepository
from app.repositories.subject_repository import SubjectRepository
from app.repositories.user_repository import UserRepository
from app.services.activity_service import ActivityService
from app.services.auth_service import AuthService
from app.services.consent_service import ConsentService
from app.services.enrollment_service import EnrollmentService
from app.services.subject_service import SubjectService

logger = logging.getLogger(__name__)

# auto_error=False: missing or malformed headers produce our own 401 Error body.
bearer_scheme = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Iterator[Session]:
    """One transaction per request: commit on success, roll back on any error."""
    factory: sessionmaker[Session] = request.app.state.session_factory
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


AppSettings = Annotated[Settings, Depends(get_settings)]


def get_embedder(request: Request) -> Embedder:
    embedder: Embedder = request.app.state.embedder
    return embedder


AppEmbedder = Annotated[Embedder, Depends(get_embedder)]


def get_user_repository(db: DbSession) -> UserRepository:
    return UserRepository(db)


def get_subject_repository(db: DbSession) -> SubjectRepository:
    return SubjectRepository(db)


def get_subject_service(
    subjects: Annotated[SubjectRepository, Depends(get_subject_repository)],
) -> SubjectService:
    return SubjectService(subjects)


def get_enrollment_service(
    db: DbSession,
    subjects: Annotated[SubjectRepository, Depends(get_subject_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> EnrollmentService:
    return EnrollmentService(subjects, EnrollmentRepository(db), users)


def get_auth_service(
    request: Request, users: Annotated[UserRepository, Depends(get_user_repository)]
) -> AuthService:
    passwords: PasswordService = request.app.state.password_service
    return AuthService(users, passwords, request.app.state.settings)


def get_consent_service(settings: AppSettings) -> ConsentService:
    return ConsentService(settings)


def _client_key(request: Request) -> str:
    """Connection peer address; forwarding headers are never consulted."""
    return request.client.host if request.client else "unknown"


def enforce_login_rate_limit(request: Request) -> None:
    limiter: RateLimiter = request.app.state.login_rate_limiter
    limiter.check(_client_key(request))


def enforce_register_rate_limit(request: Request) -> None:
    limiter: RateLimiter = request.app.state.register_rate_limiter
    limiter.check(_client_key(request))


def enforce_chat_rate_limit(request: Request) -> None:
    limiter: RateLimiter = request.app.state.chat_rate_limiter
    limiter.check(_client_key(request))


def authenticate(
    credentials: HTTPAuthorizationCredentials | None, settings: Settings, users: UserRepository
) -> User:
    """Authenticate the Bearer token; the user, and therefore the role, comes from the database."""
    challenge = {"WWW-Authenticate": "Bearer"}
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError(TOKEN_ERROR_MESSAGE, headers=challenge)
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except UnauthorizedError:
        logger.info("token rejected")
        raise
    user = users.get_by_id(user_id)
    if user is None:
        logger.info("token rejected: unknown user id=%s", user_id)
        raise UnauthorizedError(TOKEN_ERROR_MESSAGE, headers=challenge)
    return user


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: AppSettings,
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> User:
    return authenticate(credentials, settings, users)


CurrentUser = Annotated[User, Depends(get_current_user)]


def _require_role(role: UserRole) -> Callable[[User], User]:
    def guard(user: CurrentUser) -> User:
        if user.role is not role:
            raise ForbiddenError("You do not have permission to perform this action")
        return user

    return guard


require_teacher = _require_role(UserRole.TEACHER)
require_student = _require_role(UserRole.STUDENT)


def require_teacher_activity(
    teacher: Annotated[User, Depends(require_teacher)], settings: AppSettings
) -> User:
    """The teacher of an installation that switched the capability on; others see a 404.

    The role check runs first, so a student or an anonymous caller gets the same refusal whether
    or not the capability is on.
    """
    if not settings.teacher_activity_enabled:
        raise NotFoundError("Resource not found")
    return teacher


def get_activity_db(
    request: Request,
    teacher: Annotated[User, Depends(require_teacher_activity)],
    request_db: DbSession,
) -> Iterator[Session]:
    """A session of its own for the activity read: one read-only `REPEATABLE READ` snapshot.

    The marker of the subject and the facts it filters must come from the same moment: with the
    default level each statement sees what was committed at its own start, so a read that overlaps
    the commit of a removal could pair the old marker with the new cohort. The level cannot change
    after a statement ran, and the authentication of the request has run some in the shared
    session, so the read gets its own and sets the level before its first statement.

    The shared session is closed first: it only authenticated the caller, and keeping its
    connection while a second one is taken would hold two pooled connections per request, so that
    a burst of reads could take the whole pool and block every other route (review finding M-1).
    The authenticated user keeps the attributes already loaded; nothing else reads that session.
    """
    del teacher  # ordering only: the caller is authenticated before the snapshot opens
    request_db.close()
    factory: sessionmaker[Session] = request.app.state.session_factory
    session = factory()
    try:
        session.connection(
            execution_options={"isolation_level": "REPEATABLE READ", "postgresql_readonly": True}
        )
        yield session
    finally:
        session.rollback()
        session.close()


def get_activity_service(db: Annotated[Session, Depends(get_activity_db)]) -> ActivityService:
    return ActivityService(SubjectRepository(db), ActivityRepository(db))
