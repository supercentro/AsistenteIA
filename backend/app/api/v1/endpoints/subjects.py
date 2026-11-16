import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import CurrentUser, DbSession, get_subject_service, require_teacher
from app.api.transaction import commit_or_rollback
from app.models.user import User
from app.schemas.subject import SubjectCreate, SubjectResponse
from app.services.subject_service import SubjectService

router = APIRouter(prefix="/subjects", tags=["Subjects"])

Service = Annotated[SubjectService, Depends(get_subject_service)]
Teacher = Annotated[User, Depends(require_teacher)]


@router.get("", response_model=list[SubjectResponse])
def list_subjects(user: CurrentUser, service: Service) -> list[SubjectResponse]:
    """Teachers see the subjects they teach, students the ones they are enrolled in."""
    return [SubjectResponse.model_validate(item) for item in service.list_visible(user)]


@router.post("", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
def create_subject(
    body: SubjectCreate, teacher: Teacher, service: Service, db: DbSession
) -> SubjectResponse:
    subject = service.create(teacher, body)
    commit_or_rollback(db)  # stored before the 201 is built
    return SubjectResponse.model_validate(subject)


@router.get("/{subject_id}", response_model=SubjectResponse)
def get_subject(subject_id: uuid.UUID, user: CurrentUser, service: Service) -> SubjectResponse:
    return SubjectResponse.model_validate(service.get_visible(user, subject_id))


@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject(
    subject_id: uuid.UUID, teacher: Teacher, service: Service, db: DbSession
) -> Response:
    service.delete(teacher, subject_id)
    commit_or_rollback(db)  # the deletion is durable before the 204 is built
    return Response(status_code=status.HTTP_204_NO_CONTENT)
