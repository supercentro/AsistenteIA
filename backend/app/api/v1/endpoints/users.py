from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbSession, get_consent_service
from app.schemas.consent import ConsentRequest
from app.schemas.user import UserResponse
from app.services.consent_service import ConsentService

router = APIRouter(prefix="/users", tags=["Auth"])


@router.get("/me", response_model=UserResponse)
def read_me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.post("/me/consent", response_model=UserResponse)
def record_consent(
    body: ConsentRequest,
    user: CurrentUser,
    service: Annotated[ConsentService, Depends(get_consent_service)],
    db: DbSession,
) -> UserResponse:
    """Record acceptance of the current privacy-policy version (updates version and date).

    The evidence is committed here, before the response is built: a database refusal (for example a
    missing privilege) becomes an error response and never a 200 without stored evidence.
    """
    updated = service.record(user, body.consent_version)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return UserResponse.model_validate(updated)
