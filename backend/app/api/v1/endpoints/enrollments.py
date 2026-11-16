import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import DbSession, get_enrollment_service, require_teacher
from app.api.transaction import commit_or_rollback
from app.models.user import User
from app.repositories.enrollment_repository import EnrollmentRow
from app.schemas.enrollment import EnrollmentRequest, EnrollmentResponse
from app.services.enrollment_service import EnrollmentService

router = APIRouter(prefix="/subjects/{subject_id}/enrollments", tags=["Enrollments"])

Service = Annotated[EnrollmentService, Depends(get_enrollment_service)]
Teacher = Annotated[User, Depends(require_teacher)]


def _to_response(row: EnrollmentRow) -> EnrollmentResponse:
    return EnrollmentResponse(
        id=row.enrollment.id,
        subject_id=row.enrollment.subject_id,
        student_id=row.enrollment.student_id,
        student_email=row.student_email,
        created_at=row.enrollment.created_at,
    )


@router.get("", response_model=list[EnrollmentResponse])
def list_enrollments(
    subject_id: uuid.UUID, teacher: Teacher, service: Service
) -> list[EnrollmentResponse]:
    return [_to_response(row) for row in service.list_for_subject(teacher, subject_id)]


@router.post("", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
def enroll_student(
    subject_id: uuid.UUID,
    body: EnrollmentRequest,
    teacher: Teacher,
    service: Service,
    db: DbSession,
) -> EnrollmentResponse:
    row = service.enroll(teacher, subject_id, body.student_email)
    commit_or_rollback(db)  # stored before the 201 is built
    return _to_response(row)


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_enrollment(
    subject_id: uuid.UUID,
    student_id: uuid.UUID,
    teacher: Teacher,
    service: Service,
    db: DbSession,
) -> Response:
    service.remove(teacher, subject_id, student_id)
    commit_or_rollback(db)  # the removal is durable before the 204 is built
    return Response(status_code=status.HTTP_204_NO_CONTENT)
