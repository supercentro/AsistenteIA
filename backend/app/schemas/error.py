from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Common `Error` schema of docs/api-spec.yml."""

    code: str
    message: str
    details: dict[str, object] | None = None
