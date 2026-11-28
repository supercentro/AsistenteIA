"""Counting, suppression and window rules of the topic ranking.

Change `frequent-questions-and-topics`.

The service is exercised with in-memory repositories; the SQL is covered by the integration tests.
Fictitious data only.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.errors import NotFoundError
from app.models.topic import TopicSource
from app.repositories.activity_repository import AnswerFact, QuestionFact, SourceFact
from app.repositories.topic_repository import MaterialFact, StoredTopic
from app.schemas.topic import TopicRankingResponse
from app.services.topic_ranking_service import TopicRankingService

TEACHER, SUBJECT = uuid.uuid4(), uuid.uuid4()
DOC_A, DOC_B = uuid.UUID(int=1), uuid.UUID(int=2)
TODAY = date(2026, 3, 31)  # Tuesday: the last ended week is 23-29 March
LAST_MONDAY = date(2026, 3, 23)
FIRST_MONDAY = LAST_MONDAY - timedelta(weeks=11)
STUDENTS = [uuid.UUID(int=100 + n) for n in range(8)]


def topic(title: str, start: int, end: int, number: int) -> StoredTopic:
    return StoredTopic(uuid.UUID(int=1000 + number), title, start, end)


def material(
    document: uuid.UUID = DOC_A,
    name: str = "a.pdf",
    *topics: StoredTopic,
    changed: datetime | None = None,
    pages: bool = True,
) -> MaterialFact:
    return MaterialFact(
        document_id=document,
        filename=name,
        has_pages=pages,
        source=TopicSource.TEACHER if topics else None,
        ranges_changed_at=changed,
        topics=topics,
    )


class World:
    def __init__(self, *documents: MaterialFact, marker: datetime | None = None) -> None:
        self.documents = list(documents)
        self.marker = marker
        self.asked: list[QuestionFact] = []
        self.answered: list[AnswerFact] = []
        self.reads: list[str] = []

    # repositories -----------------------------------------------------------------------------
    def get_for_teacher(self, subject_id: uuid.UUID, teacher_id: uuid.UUID) -> object | None:
        if subject_id == SUBJECT and teacher_id == TEACHER:
            return SimpleNamespace(last_unenrolment_at=self.marker)
        return None

    def questions(self, *, start: datetime, end: datetime, **_: object) -> list[QuestionFact]:
        self.reads.append("questions")
        return [q for q in self.asked if start <= q.asked_at < end]

    def answers(self, *, start: datetime, end: datetime, **_: object) -> list[AnswerFact]:
        self.reads.append("answers")
        return [a for a in self.answered if start <= a.answered_at < end]

    def material(self, **_: object) -> list[MaterialFact]:
        return self.documents

    # builders ---------------------------------------------------------------------------------
    def cite(
        self,
        student: uuid.UUID,
        *pages: int,
        document: uuid.UUID = DOC_A,
        day: date = LAST_MONDAY,
        cited: bool = True,
        also: tuple[tuple[uuid.UUID, int], ...] = (),
    ) -> None:
        when = datetime(day.year, day.month, day.day, 10, tzinfo=UTC)
        places = [(document, page) for page in pages] + list(also)
        marks = " ".join(f"[{n}]" for n in range(1, len(places) + 1)) if cited else ""
        sources = tuple(
            SourceFact(rank=n, document_id=doc, filename="x.pdf", page_number=page)
            for n, (doc, page) in enumerate(places, start=1)
        )
        self.asked.append(QuestionFact(student, when))
        self.answered.append(AnswerFact(student, when, f"Respuesta ficticia {marks}", sources))

    def read(self) -> TopicRankingResponse:
        service = TopicRankingService(self, self, self, today=lambda: TODAY)  # type: ignore[arg-type]
        return service.get(TEACHER, SUBJECT)


def figures(response: TopicRankingResponse) -> list[tuple[str, int]]:
    return [(t.title, t.answers) for t in response.topics]


def test_an_answer_counts_once_per_topic_and_in_every_topic_it_cites() -> None:
    world = World(material(DOC_A, "a.pdf", topic("Uno", 1, 3, 1), topic("Dos", 4, 6, 2)))
    for student in STUDENTS[:5]:
        world.cite(student, 1, 2, 3, 5)

    assert figures(world.read()) == [("Dos", 5), ("Uno", 5)]


def test_only_cited_answers_and_pages_inside_the_range_count() -> None:
    world = World(material(DOC_A, "a.pdf", topic("Uno", 2, 3, 1)))
    for student in STUDENTS[:5]:
        world.cite(student, 2)
        world.cite(student, 2, cited=False)  # retrieved only
        world.cite(student, 1)  # before the topic
        world.cite(student, 4)  # after it
        world.cite(student, 2, document=DOC_B)  # another document

    assert figures(world.read()) == [("Uno", 5)]


def test_a_topic_needs_five_distinct_students() -> None:
    world = World(material(DOC_A, "a.pdf", topic("Cuatro", 1, 1, 1), topic("Cinco", 2, 2, 2)))
    for student in STUDENTS[:4]:
        for _ in range(8):
            world.cite(student, 1)
    for student in STUDENTS[:5]:
        world.cite(student, 2)

    response = world.read()

    assert figures(response) == [("Cinco", 5)]
    assert response.topics_defined == 2


def test_a_subject_with_fewer_than_five_active_students_ranks_nothing() -> None:
    world = World(material(DOC_A, "a.pdf", topic("Uno", 1, 1, 1)))
    for student in STUDENTS[:4]:
        world.cite(student, 1)

    assert world.read().topics == []


def test_at_most_five_topics_in_a_fixed_order() -> None:
    topics = [topic(f"T{n}", n, n, n) for n in range(1, 8)]
    world = World(material(DOC_A, "a.pdf", *topics))
    for student in STUDENTS[:5]:
        world.cite(student, 1, 2, 3, 4, 5, 6, 7)
    world.cite(STUDENTS[5], 7)

    assert figures(world.read()) == [("T7", 6), ("T1", 5), ("T2", 5), ("T3", 5), ("T4", 5)]


def test_equal_titles_are_not_added_and_name_each_other() -> None:
    world = World(
        material(DOC_A, "a.pdf", topic("Normalization", 1, 1, 1)),
        material(DOC_B, "b.pdf", topic("normalization", 1, 1, 2)),
    )
    for student in STUDENTS[:5]:
        world.cite(student, 1)
        world.cite(student, 1, document=DOC_B)
    world.cite(STUDENTS[5], 1, document=DOC_B)

    response = world.read()

    assert [(t.filename, t.answers, t.also_in) for t in response.topics] == [
        ("b.pdf", 6, ["a.pdf"]),
        ("a.pdf", 5, ["b.pdf"]),
    ]


def test_each_topic_says_its_document_pages_and_start() -> None:
    world = World(material(DOC_A, "a.pdf", topic("Uno", 2, 4, 1)))
    for student in STUDENTS[:5]:
        world.cite(student, 3)

    ranked = world.read().topics[0]

    assert (ranked.document_id, ranked.filename) == (DOC_A, "a.pdf")
    assert (ranked.start_page, ranked.end_page, ranked.counted_since) == (2, 4, FIRST_MONDAY)


def test_a_changed_document_counts_only_the_weeks_after_the_change() -> None:
    changed = datetime(2026, 3, 11, 9, tzinfo=UTC)  # week of 9 March
    world = World(
        material(DOC_A, "a.pdf", topic("Cambiado", 1, 1, 1), changed=changed),
        material(DOC_B, "b.pdf", topic("Intacto", 1, 1, 2)),
    )
    for student in STUDENTS[:5]:
        for day in (date(2026, 3, 3), date(2026, 3, 10), date(2026, 3, 17)):
            world.cite(student, 1, day=day)
            world.cite(student, 1, document=DOC_B, day=day)

    response = world.read()

    assert figures(response) == [("Intacto", 15), ("Cambiado", 5)]
    assert response.topics[1].counted_since == date(2026, 3, 16)
    assert [(r.filename, r.counting_from) for r in response.restarted_documents] == [
        ("a.pdf", date(2026, 3, 16))
    ]


def test_a_document_changed_in_the_last_ended_week_has_no_figure_yet() -> None:
    changed = datetime(2026, 3, 24, 9, tzinfo=UTC)
    world = World(material(DOC_A, "a.pdf", topic("Uno", 1, 1, 1), changed=changed))
    for student in STUDENTS[:5]:
        world.cite(student, 1)

    response = world.read()

    assert response.topics == []
    assert response.restarted_documents[0].counting_from == date(2026, 3, 30)


def test_documents_without_topics_are_named_with_the_reason() -> None:
    world = World(
        material(DOC_A, "a.pdf", topic("Uno", 1, 1, 1)),
        material(DOC_B, "b.pdf"),
        material(uuid.UUID(int=3), "c.md", pages=False),
    )

    response = world.read()

    assert [(d.filename, d.reason) for d in response.documents_without_topics] == [
        ("b.pdf", "not_defined"),
        ("c.md", "no_pages"),
    ]


def test_the_window_is_twelve_ended_weeks() -> None:
    window = World().read().window

    assert (window.start, window.end, window.weeks) == (FIRST_MONDAY, date(2026, 3, 29), 12)


def test_weeks_up_to_the_unenrolment_are_left_out() -> None:
    marker = datetime(2026, 3, 18, tzinfo=UTC)
    world = World(material(DOC_A, "a.pdf", topic("Uno", 1, 1, 1)), marker=marker)
    for student in STUDENTS[:5]:
        world.cite(student, 1, day=date(2026, 3, 17))
        world.cite(student, 1)

    response = world.read()

    assert response.window.start == LAST_MONDAY and figures(response) == [("Uno", 5)]


def test_with_no_whole_week_no_message_is_read() -> None:
    marker = datetime(2026, 3, 25, tzinfo=UTC)
    world = World(material(DOC_A, "a.pdf", topic("Uno", 1, 1, 1)), marker=marker)

    response = world.read()

    assert response.window.weeks == 0 and response.topics == [] and world.reads == []


def test_another_teacher_gets_not_found_and_nothing_is_read() -> None:
    world = World()
    service = TopicRankingService(world, world, world, today=lambda: TODAY)  # type: ignore[arg-type]

    with pytest.raises(NotFoundError):
        service.get(uuid.uuid4(), SUBJECT)

    assert world.reads == []


def test_no_message_is_read_when_the_subject_has_no_topic() -> None:
    world = World(material(DOC_A, "a.pdf"))
    for student in STUDENTS[:5]:
        world.cite(student, 1)

    response = world.read()

    assert world.reads == []
    assert (response.topics_defined, response.topics) == (0, [])
    assert [d.filename for d in response.documents_without_topics] == ["a.pdf"]


def test_fewer_than_five_active_students_give_nothing_even_with_five_cited() -> None:
    """The fifth student asked before the window and was answered inside it."""
    world = World(material(DOC_A, "a.pdf", topic("Uno", 1, 3, 1)))
    for student in STUDENTS[:5]:
        world.cite(student, 1)
    world.asked.pop()

    assert world.read().topics == []
