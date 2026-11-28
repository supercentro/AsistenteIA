"""Topics of one document, read and written by its teacher (change `frequent-questions-and-topics`).

Material metadata only: titles and page positions of a file of the subject. No field can hold
anything about a student.
"""

import unicodedata
import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.models.topic import TITLE_MAX_LENGTH, TopicSource
from app.schemas.activity import ActivityWindow
from app.schemas.validators import ensure_no_control_characters, has_visible_character

MAX_TOPICS = 100
# Far above any real file; it only keeps numbers inside the integer column.
MAX_PAGE = 100_000
_MAX_RAW_TITLE = 1_000
_MAX_REVISION = 2_000_000_000


def _clean_title(value: str) -> str:
    """One line of plain text: control, direction and surrogate characters are refused."""
    ensure_no_control_characters(value)
    if any(unicodedata.category(char) == "Cs" for char in value):
        raise ValueError("contains characters that are not text")
    collapsed = " ".join(value.split())
    if not 1 <= len(collapsed) <= TITLE_MAX_LENGTH:
        raise ValueError(f"must have between 1 and {TITLE_MAX_LENGTH} characters")
    if not has_visible_character(collapsed):
        raise ValueError("must have a visible character")
    return collapsed


Title = Annotated[
    str,
    StringConstraints(strict=True, max_length=_MAX_RAW_TITLE),
    AfterValidator(_clean_title),
]
Page = Annotated[int, Field(strict=True, ge=1, le=MAX_PAGE)]
UnavailableReason = Literal["not_ready", "no_pages"]


class TopicEntry(BaseModel):
    """A title and an inclusive range of page positions."""

    model_config = ConfigDict(extra="forbid")

    title: Title
    start_page: Page
    end_page: Page


class DocumentTopicsUpdate(BaseModel):
    """The whole set that replaces the stored one, with the revision it was read with."""

    model_config = ConfigDict(extra="forbid")

    revision: Annotated[int, Field(strict=True, ge=0, le=_MAX_REVISION)]
    topics: Annotated[list[TopicEntry], Field(max_length=MAX_TOPICS)]


class TopicView(BaseModel):
    """A stored topic (stored titles are not validated again on the way out)."""

    title: str
    start_page: int
    end_page: int


class RankedTopic(BaseModel):
    """A topic of one document and the answers that cited its pages (never a difficulty)."""

    topic_id: uuid.UUID
    title: str
    document_id: uuid.UUID
    filename: str
    start_page: int
    end_page: int
    counted_since: date
    answers: int
    # Other current documents with a topic of the same title: names only, never added.
    also_in: list[str]


class DocumentWithoutTopics(BaseModel):
    document_id: uuid.UUID
    filename: str
    reason: Literal["not_defined", "no_pages"]


class RestartedDocument(BaseModel):
    """A document counted from a later week than the window, because its pages changed."""

    document_id: uuid.UUID
    filename: str
    counting_from: date


class TopicRankingResponse(BaseModel):
    window: ActivityWindow
    minimum_group: int
    topics_defined: int
    topics: list[RankedTopic]
    documents_without_topics: list[DocumentWithoutTopics]
    restarted_documents: list[RestartedDocument]


class DocumentTopicsResponse(BaseModel):
    document_id: uuid.UUID
    filename: str
    editable: bool
    reason: UnavailableReason | None
    last_page: int | None
    revision: int
    source: TopicSource | None
    # The Monday from which the figures count, when the pages were changed after the first set.
    counting_from: date | None
    topics: list[TopicView]
