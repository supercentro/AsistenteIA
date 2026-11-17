from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import CurrentUser, DbSession, get_consent_service, require_student
from app.api.transaction import commit_or_rollback
from app.models.user import User
from app.repositories.conversation_repository import ConversationRepository
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
    commit_or_rollback(db)
    return UserResponse.model_validate(updated)


@router.delete("/me/conversations", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_conversations(
    student: Annotated[User, Depends(require_student)],
    db: DbSession,
) -> Response:
    """Delete all of the current student's conversations (right to erasure)."""
    repo = ConversationRepository(db)
    repo.delete_all_by_student(student.id)
    commit_or_rollback(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
