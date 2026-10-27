from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.errors import ServiceUnavailableError
from app.schemas.error import ErrorResponse
from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": ErrorResponse, "description": "Database unreachable"}},
)
def health(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    """Liveness and database connectivity check."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise ServiceUnavailableError("Service unavailable") from None
    return HealthResponse(status="ok")
