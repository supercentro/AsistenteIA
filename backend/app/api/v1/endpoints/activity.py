"""Aggregate activity of a subject for its owning teacher (change `activity-events-and-metrics`).

Read only, switched off by `TEACHER_ACTIVITY_ENABLED` (default off). Another teacher's subject and
an unknown subject give the same 404; a student and an anonymous caller are refused before the
setting is looked at.
"""

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_activity_service, require_teacher_activity
from app.models.user import User
from app.schemas.activity import ActivityResponse
from app.schemas.error import ErrorResponse
from app.services.activity_service import ActivityService

router = APIRouter(prefix="/subjects", tags=["Activity"])

Service = Annotated[ActivityService, Depends(get_activity_service)]
Teacher = Annotated[User, Depends(require_teacher_activity)]
_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid token"},
    403: {"model": ErrorResponse, "description": "Authenticated but not a teacher"},
    404: {
        "model": ErrorResponse,
        "description": "The subject does not exist or is not yours, or the capability is off",
    },
    500: {"model": ErrorResponse, "description": "Unexpected error"},
    503: {"model": ErrorResponse, "description": "Database unavailable"},
}


@router.get("/{subject_id}/activity", response_model=ActivityResponse, responses=_ERRORS)
def get_subject_activity(
    subject_id: uuid.UUID,
    teacher: Teacher,
    service: Service,
    start: Annotated[date | None, Query(description="First day of the window")] = None,
    end: Annotated[date | None, Query(description="Last day of the window")] = None,
    granularity: Annotated[Literal["week"], Query()] = "week",
) -> ActivityResponse:
    return service.get(teacher.id, subject_id, start=start, end=end)
