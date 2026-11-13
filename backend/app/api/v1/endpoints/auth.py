from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    DbSession,
    enforce_login_rate_limit,
    enforce_register_rate_limit,
    get_auth_service,
)
from app.api.transaction import commit_or_rollback
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_register_rate_limit)],
)
def register(body: RegisterRequest, service: AuthServiceDep, db: DbSession) -> UserResponse:
    """Public registration: always creates a student; stored before the 201 is built."""
    user = service.register_student(body.name, body.email, body.password)
    commit_or_rollback(db)
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_login_rate_limit)],
)
def login(body: LoginRequest, service: AuthServiceDep) -> TokenResponse:
    return service.login(body.email, body.password)
