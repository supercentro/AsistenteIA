from pydantic import BaseModel, Field


class ConsentRequest(BaseModel):
    consent_version: str = Field(min_length=1, max_length=20)
