"""The most cited topics of a subject, for its owning teacher.

Change `frequent-questions-and-topics`.

Computed on read and stored nowhere, with the rules of the teacher activity: only ended weeks, at
most `MAX_WEEKS`, only after the last unenrolment, only students currently enrolled, and a topic
shown only when `MINIMUM_GROUP` distinct students are behind it. A document whose page ranges
changed counts only the weeks after the change. No request parameter moves any of this.

The figure of a topic is the number of answers that cited a fragment of its document on one of its
pages. It is not a measure of difficulty, and it is not anonymous: with accounts of its own a
teacher can learn which topic one student's answers cited (open risk, docs/technical-debt.md).
"""

import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from app.core.errors import NotFoundError
from app.repositories.activity_repository import ActivityRepository, AnswerFact
from app.repositories.subject_repository import SubjectRepository
from app.repositories.topic_repository import MaterialFact, StoredTopic, TopicRepository
from app.schemas.activity import ActivityWindow
from app.schemas.topic import (
    DocumentWithoutTopics,
    RankedTopic,
    RestartedDocument,
    TopicRankingResponse,
)
from app.services.activity_service import (
    MINIMUM_GROUP,
    ended_weeks_today,
    first_week_after,
    whole_weeks,
)
from app.services.prompt_builder import attribution_of
from app.services.subject_service import SUBJECT_NOT_FOUND_MESSAGE

MAX_RANKED = 5


def _utc_today() -> date:
    return ended_weeks_today(datetime.now(UTC))


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _same_title(title: str) -> str:
    return " ".join(title.split()).casefold()


@dataclass
class _Tally:
    answers: int = 0
    students: set[uuid.UUID] = field(default_factory=set)


class TopicRankingService:
    def __init__(
        self,
        subjects: SubjectRepository,
        activity: ActivityRepository,
        topics: TopicRepository,
        *,
        today: Callable[[], date] = _utc_today,
    ) -> None:
        self._subjects = subjects
        self._activity = activity
        self._topics = topics
        self._today = today

    def get(self, teacher_id: uuid.UUID, subject_id: uuid.UUID) -> TopicRankingResponse:
        subject = self._subjects.get_for_teacher(subject_id, teacher_id)
        if subject is None:
            raise NotFoundError(SUBJECT_NOT_FOUND_MESSAGE)  # same answer as an unknown subject
        first, last, weeks = whole_weeks(self._today(), subject.last_unenrolment_at)
        scope = {"teacher_id": teacher_id, "subject_id": subject_id}
        material = self._topics.material(**scope)
        starts = {
            document.document_id: (
                first
                if document.ranges_changed_at is None
                else max(first, first_week_after(document.ranges_changed_at))
            )
            for document in material
        }
        ranked: list[RankedTopic] = []
        # With no whole week, or no topic in the subject, no message is read at all.
        if weeks and any(document.topics for document in material):
            until = _midnight(first + timedelta(days=7 * weeks))
            since = _midnight(first)
            asked = self._activity.questions(
                teacher_id=teacher_id, subject_id=subject_id, start=since, end=until
            )
            if len({question.student_id for question in asked}) >= MINIMUM_GROUP:
                answers = self._activity.answers(
                    teacher_id=teacher_id, subject_id=subject_id, start=since, end=until
                )
                ranked = self._rank(material, starts, answers)
        return TopicRankingResponse(
            window=ActivityWindow(
                start=first if weeks else last + timedelta(days=1),
                end=last,
                granularity="week",
                weeks=weeks,
            ),
            minimum_group=MINIMUM_GROUP,
            topics_defined=sum(len(document.topics) for document in material),
            topics=ranked,
            documents_without_topics=[
                DocumentWithoutTopics(
                    document_id=document.document_id,
                    filename=document.filename,
                    reason="not_defined" if document.has_pages else "no_pages",
                )
                for document in material
                if not document.topics
            ],
            restarted_documents=[
                RestartedDocument(
                    document_id=document.document_id,
                    filename=document.filename,
                    counting_from=starts[document.document_id],
                )
                for document in material
                if document.topics and starts[document.document_id] > first
            ],
        )

    @staticmethod
    def _rank(
        material: list[MaterialFact],
        starts: dict[uuid.UUID, date],
        answers: list[AnswerFact],
    ) -> list[RankedTopic]:
        documents = {document.document_id: document for document in material if document.topics}
        tallies: dict[uuid.UUID, _Tally] = defaultdict(_Tally)
        for answer in answers:
            ranks = [source.rank for source in answer.sources]
            if attribution_of(answer.content, ranks) != "cited":
                continue
            cited: set[uuid.UUID] = set()  # topics, each once per answer
            for source in answer.sources:
                if source.document_id is None or source.page_number is None:
                    continue
                document = documents.get(source.document_id)
                if document is None:
                    continue
                if answer.answered_at < _midnight(starts[document.document_id]):
                    continue
                cited.update(
                    topic.id
                    for topic in document.topics
                    if topic.start_page <= source.page_number <= topic.end_page
                )
            for topic_id in cited:
                tallies[topic_id].answers += 1
                tallies[topic_id].students |= {answer.student_id}

        titled: dict[str, set[uuid.UUID]] = defaultdict(set)
        for document in documents.values():
            for topic in document.topics:
                titled[_same_title(topic.title)] |= {document.document_id}

        eligible: list[tuple[MaterialFact, StoredTopic, int]] = [
            (document, topic, tallies[topic.id].answers)
            for document in documents.values()
            for topic in document.topics
            if topic.id in tallies and len(tallies[topic.id].students) >= MINIMUM_GROUP
        ]
        eligible.sort(
            key=lambda item: (
                -item[2],
                item[1].title,
                item[0].filename,
                str(item[0].document_id),
                item[1].start_page,
                str(item[1].id),
            )
        )
        return [
            RankedTopic(
                topic_id=topic.id,
                title=topic.title,
                document_id=document.document_id,
                filename=document.filename,
                start_page=topic.start_page,
                end_page=topic.end_page,
                counted_since=starts[document.document_id],
                answers=figure,
                also_in=sorted(
                    documents[other].filename
                    for other in titled[_same_title(topic.title)]
                    if other != document.document_id
                ),
            )
            for document, topic, figure in eligible[:MAX_RANKED]
        ]
