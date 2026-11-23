"""Aggregate activity of a subject, for its teacher (change `activity-events-and-metrics`).

Numbers, dates and the file name of a document of the subject only: no field can hold the text of
a question or an answer, an identifier, a name or an e-mail of a student. A figure that comes from
fewer students than the minimum group is `null`. `tests/unit/test_activity_schema_shape.py`
fails when a field is added without review.
"""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel


class ActivityWindow(BaseModel):
    """The window actually computed: whole weeks, Monday to Sunday, in UTC."""

    start: date
    end: date
    granularity: Literal["week"]
    weeks: int


class ActivityPeriod(BaseModel):
    """Questions of one week; `count` is null when fewer than the minimum group asked."""

    period_start: date
    count: int | None


class ActivityDocument(BaseModel):
    """How many answers cited the document (never evidence that the material was used)."""

    document_id: uuid.UUID | None  # null when the document was deleted
    filename: str
    cited_appearances: int | None


class ActivityResponse(BaseModel):
    window: ActivityWindow
    minimum_group: int
    enrolled_students: int
    active_students: int | None
    questions: list[ActivityPeriod]
    no_material_rate: float | None
    no_cited_source_rate: float | None
    documents: list[ActivityDocument]
    suppressed: bool
