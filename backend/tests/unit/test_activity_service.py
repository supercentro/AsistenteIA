"""Aggregation, suppression and window rules of the teacher activity (tasks 1.1 to 1.3).

The service is exercised with an in-memory repository; the SQL itself is covered by the
integration tests. Fictitious data only.
"""

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.errors import AppError, NotFoundError
from app.repositories.activity_repository import AnswerFact, QuestionFact, SourceFact
from app.services.activity_service import MAX_WEEKS, MINIMUM_GROUP, ActivityService

TEACHER = uuid.uuid4()
SUBJECT = uuid.uuid4()
DOC_A, DOC_B = uuid.uuid4(), uuid.uuid4()
START, END = date(2026, 3, 2), date(2026, 3, 29)  # Monday to Sunday, four weeks
WEEK1, WEEK2, WEEK3, WEEK4 = (date(2026, 3, d) for d in (2, 9, 16, 23))
CITED = "Respuesta ficticia [1]."
PLAIN = "Respuesta ficticia sin marcas."


def moment(day: date, hour: int = 10) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


class FakeSubjects:
    """The owner's subject, with the marker of its last unenrolment (null: none yet)."""

    def __init__(self, owner: uuid.UUID | None = TEACHER, marker: datetime | None = None) -> None:
        self._owner = owner
        self.marker = marker

    def get_for_teacher(self, subject_id: uuid.UUID, teacher_id: uuid.UUID) -> object | None:
        if subject_id == SUBJECT and teacher_id == self._owner:
            return SimpleNamespace(last_unenrolment_at=self.marker)
        return None


class FakeRepository:
    def __init__(self, enrolled: int = 30) -> None:
        self.enrolled = enrolled
        self.question_facts: list[QuestionFact] = []
        self.answer_facts: list[AnswerFact] = []
        self.documents: list[tuple[uuid.UUID, str]] = [(DOC_A, "a.pdf"), (DOC_B, "b.pdf")]
        self.calls: list[dict[str, Any]] = []

    def enrolled_count(self, *, teacher_id: uuid.UUID, subject_id: uuid.UUID) -> int:
        return self.enrolled

    def questions(
        self, *, teacher_id: uuid.UUID, subject_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[QuestionFact]:
        self.calls.append({"teacher": teacher_id, "start": start, "end": end})
        return self.question_facts

    def answers(
        self, *, teacher_id: uuid.UUID, subject_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[AnswerFact]:
        return self.answer_facts

    def current_documents(
        self, *, teacher_id: uuid.UUID, subject_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str]]:
        return self.documents

    # builders ---------------------------------------------------------------------------------
    def turn(
        self,
        student: uuid.UUID,
        day: date,
        *,
        content: str = CITED,
        document: uuid.UUID | None = DOC_A,
        filename: str = "a.pdf",
        ranks: tuple[int, ...] = (1,),
        with_sources: bool = True,
    ) -> None:
        when = moment(day)
        self.question_facts.append(QuestionFact(student_id=student, asked_at=when))
        sources = (
            tuple(SourceFact(rank=r, document_id=document, filename=filename) for r in ranks)
            if with_sources
            else ()
        )
        self.answer_facts.append(
            AnswerFact(student_id=student, answered_at=when, content=content, sources=sources)
        )


def build(
    repo: FakeRepository, *, owner: uuid.UUID | None = TEACHER, today: date = date(2026, 3, 30)
) -> ActivityService:
    return ActivityService(FakeSubjects(owner), repo, today=lambda: today)  # type: ignore[arg-type]


def students(count: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(count)]


def get(service: ActivityService, **kwargs: Any) -> Any:
    window = {"start": START, "end": END} | kwargs
    return service.get(TEACHER, SUBJECT, **window)


def padded(repo: FakeRepository, extra_active: int = MINIMUM_GROUP) -> None:
    """Enough active students in week 1 so that the subject itself is not suppressed."""
    for student in students(extra_active):
        repo.turn(student, WEEK1)


# --- suppression of a cell (task 1.2) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("distinct", "shown"),
    [
        (MINIMUM_GROUP - 1, None),
        (MINIMUM_GROUP, 2 * MINIMUM_GROUP),
        (MINIMUM_GROUP + 1, 2 * (MINIMUM_GROUP + 1)),
    ],
    ids=["N-1", "N", "N+1"],
)
def test_a_period_is_shown_only_when_at_least_n_distinct_students_asked(
    distinct: int, shown: int | None
) -> None:
    repo = FakeRepository()
    padded(repo)
    for student in students(distinct):
        repo.turn(student, WEEK2)
        repo.turn(student, WEEK2)

    result = get(build(repo))

    week2 = next(p for p in result.questions if p.period_start == WEEK2)
    assert week2.count == shown


def test_the_same_student_asking_many_times_does_not_make_a_group() -> None:
    repo = FakeRepository()
    padded(repo)
    one = uuid.uuid4()
    for _ in range(40):
        repo.turn(one, WEEK3)

    result = get(build(repo))

    assert next(p for p in result.questions if p.period_start == WEEK3).count is None


def test_a_period_without_questions_is_suppressed_like_any_other() -> None:
    repo = FakeRepository()
    padded(repo)

    result = get(build(repo))

    assert [p.count for p in result.questions[1:]] == [None, None, None]


# --- suppression for the whole subject --------------------------------------------------------


def test_a_subject_with_fewer_than_n_active_students_shows_only_the_enrolled_count() -> None:
    repo = FakeRepository(enrolled=12)
    for student in students(MINIMUM_GROUP - 1):
        for week in (WEEK1, WEEK2, WEEK3):
            repo.turn(student, week)

    result = get(build(repo))

    assert result.enrolled_students == 12
    assert result.active_students is None
    assert all(p.count is None for p in result.questions)
    assert result.no_material_rate is None and result.no_cited_source_rate is None
    assert all(d.cited_appearances is None for d in result.documents)
    assert result.suppressed is True


def test_exactly_n_active_students_are_shown() -> None:
    repo = FakeRepository()
    padded(repo, MINIMUM_GROUP)

    result = get(build(repo))

    assert result.active_students == MINIMUM_GROUP
    assert result.minimum_group == MINIMUM_GROUP == 5


def test_active_students_are_distinct_over_the_whole_window() -> None:
    repo = FakeRepository()
    group = students(MINIMUM_GROUP + 2)
    for index, student in enumerate(group):
        repo.turn(student, (WEEK1, WEEK2, WEEK3, WEEK4)[index % 4])
        repo.turn(student, WEEK4)

    assert get(build(repo)).active_students == MINIMUM_GROUP + 2


# --- rates (task 1.1) -------------------------------------------------------------------------


def test_the_two_rates_use_the_derived_attribution() -> None:
    repo = FakeRepository()
    group = students(MINIMUM_GROUP)
    for student in group:  # five answers that cite their source
        repo.turn(student, WEEK1, content=CITED)
    for student in group[:3]:  # three answers that only retrieved material
        repo.turn(student, WEEK2, content=PLAIN)
    for student in group[:2]:  # two answers with no material at all
        repo.turn(student, WEEK3, with_sources=False, content="No hay material.")

    result = get(build(repo))

    assert result.no_material_rate == pytest.approx(0.2)  # 2 of 10
    assert result.no_cited_source_rate == pytest.approx(0.5)  # 3 + 2 of 10


def test_a_rate_whose_denominator_has_fewer_than_n_students_is_null() -> None:
    repo = FakeRepository()
    group = students(MINIMUM_GROUP)
    for student in group:  # everybody asked, but only four answers were stored
        repo.question_facts.append(QuestionFact(student_id=student, asked_at=moment(WEEK1)))
    for student in group[:-1]:
        repo.turn(student, WEEK1)

    result = get(build(repo))

    assert result.active_students == MINIMUM_GROUP
    assert result.no_material_rate is None
    assert result.no_cited_source_rate is None


# --- appearances of cited sources per document (task 1.1, D-M6) ------------------------------


@pytest.mark.parametrize(
    ("distinct", "shown"),
    [
        (MINIMUM_GROUP - 1, None),
        (MINIMUM_GROUP, MINIMUM_GROUP),
        (MINIMUM_GROUP + 1, MINIMUM_GROUP + 1),
    ],
    ids=["N-1", "N", "N+1"],
)
def test_a_document_figure_needs_n_distinct_students(distinct: int, shown: int | None) -> None:
    repo = FakeRepository()
    padded(repo)  # five students cite document A in week 1 (not under test)
    for student in students(distinct):
        repo.turn(student, WEEK2, document=DOC_B, filename="b.pdf")

    result = get(build(repo))

    by_name = {d.filename: d.cited_appearances for d in result.documents}
    assert by_name["b.pdf"] == shown
    assert by_name["a.pdf"] == MINIMUM_GROUP


def test_only_cited_answers_count_as_appearances() -> None:
    repo = FakeRepository()
    for student in students(MINIMUM_GROUP):
        repo.turn(student, WEEK1, content=PLAIN, document=DOC_B, filename="b.pdf")  # retrieved only

    result = get(build(repo))

    assert {d.filename: d.cited_appearances for d in result.documents}["b.pdf"] is None


def test_an_answer_counts_once_per_document_even_with_two_cited_chunks_of_it() -> None:
    repo = FakeRepository()
    for student in students(MINIMUM_GROUP):
        repo.turn(student, WEEK1, content="Respuesta [1][2].", ranks=(1, 2))

    result = get(build(repo))

    assert {d.filename: d.cited_appearances for d in result.documents}["a.pdf"] == MINIMUM_GROUP


def test_every_current_document_is_listed_even_without_appearances() -> None:
    repo = FakeRepository()
    padded(repo)

    names = {d.filename for d in get(build(repo)).documents}

    assert names == {"a.pdf", "b.pdf"}


# --- window and buckets (task 1.3) ------------------------------------------------------------


def test_the_window_is_aligned_to_whole_weeks_monday_to_sunday() -> None:
    result = get(build(FakeRepository()), start=date(2026, 3, 4), end=date(2026, 3, 26))

    assert result.window.start == date(2026, 3, 2)
    assert result.window.end == date(2026, 3, 29)
    assert result.window.weeks == 4
    assert [p.period_start for p in result.questions] == [WEEK1, WEEK2, WEEK3, WEEK4]


def test_a_question_at_the_week_boundary_goes_to_the_right_bucket() -> None:
    repo = FakeRepository()
    group = students(MINIMUM_GROUP)
    for student in group:
        repo.question_facts.append(QuestionFact(student, datetime(2026, 3, 8, 23, 59, tzinfo=UTC)))
        repo.question_facts.append(QuestionFact(student, datetime(2026, 3, 9, 0, 0, tzinfo=UTC)))

    result = get(build(repo))

    counts = {p.period_start: p.count for p in result.questions}
    assert counts[WEEK1] == MINIMUM_GROUP and counts[WEEK2] == MINIMUM_GROUP


def test_the_repository_is_asked_for_exactly_the_aligned_window() -> None:
    repo = FakeRepository()

    get(build(repo), start=date(2026, 3, 4), end=date(2026, 3, 26))

    call = repo.calls[0]
    assert call["teacher"] == TEACHER
    assert call["start"] == datetime(2026, 3, 2, tzinfo=UTC)
    assert call["end"] == datetime(2026, 3, 30, tzinfo=UTC)  # exclusive


def test_the_window_has_at_most_twelve_weeks_which_is_within_ninety_days() -> None:
    assert MAX_WEEKS * 7 <= 90
    service = build(FakeRepository())

    ok = service.get(TEACHER, SUBJECT, start=date(2026, 1, 5), end=date(2026, 3, 29))  # 12 weeks
    assert ok.window.weeks == MAX_WEEKS

    with pytest.raises(AppError) as error:
        service.get(TEACHER, SUBJECT, start=date(2025, 12, 29), end=date(2026, 3, 29))  # 13 weeks
    assert error.value.status_code == 422


def test_an_end_before_the_start_is_refused() -> None:
    with pytest.raises(AppError) as error:
        get(build(FakeRepository()), start=date(2026, 3, 20), end=date(2026, 3, 2))

    assert error.value.status_code == 422


def test_the_default_window_ends_with_the_last_week_that_has_ended_and_has_twelve_weeks() -> None:
    result = build(FakeRepository(), today=date(2026, 3, 30)).get(TEACHER, SUBJECT)

    assert result.window.end == date(2026, 3, 29)  # today is a Monday: the open week is not shown
    assert result.window.weeks == MAX_WEEKS


# --- authorisation and shape ------------------------------------------------------------------


def test_a_subject_of_another_teacher_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        get(build(FakeRepository(), owner=uuid.uuid4()))


def test_the_response_carries_no_identifier_of_a_student_and_no_message_text() -> None:
    repo = FakeRepository()
    group = students(MINIMUM_GROUP + 1)
    for student in group:
        repo.turn(student, WEEK1)

    text = get(build(repo)).model_dump_json()

    assert "Respuesta ficticia" not in text
    assert not any(str(student) in text for student in group)


def test_suppressed_is_false_only_when_every_figure_is_shown() -> None:
    repo = FakeRepository()
    repo.documents = [(DOC_A, "a.pdf")]
    for week in (WEEK1, WEEK2, WEEK3, WEEK4):
        for student in students(MINIMUM_GROUP):
            repo.turn(student, week)

    assert get(build(repo)).suppressed is False

    repo.question_facts.pop()  # one week now has four students
    repo.answer_facts.pop()
    assert get(build(repo)).suppressed is True


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (None, date(1, 1, 5)),
        (date(1, 1, 1), date(9999, 12, 31)),
    ],
    ids=["end-at-year-one", "whole-calendar"],
)
def test_dates_next_to_the_calendar_limits_are_a_422_not_an_overflow(
    start: date | None, end: date
) -> None:
    with pytest.raises(AppError) as error:
        build(FakeRepository()).get(TEACHER, SUBJECT, start=start, end=end)

    assert error.value.status_code == 422


@pytest.mark.parametrize(
    ("start", "end"),
    [(None, date(9999, 12, 31)), (date(9999, 12, 20), date(9999, 12, 31))],
    ids=["end-at-the-limit", "start-and-end-at-the-limit"],
)
def test_an_end_in_the_far_future_is_cut_at_the_last_ended_week_and_never_overflows(
    start: date | None, end: date
) -> None:
    """The open week and the future are never shown (A2b), so these no longer reach the limit."""
    result = build(FakeRepository()).get(TEACHER, SUBJECT, start=start, end=end)

    assert result.window.end <= date(2026, 3, 29)
    assert result.window.weeks in (0, MAX_WEEKS)


def test_a_window_in_the_future_is_valid_and_has_no_weeks() -> None:
    result = get(build(FakeRepository()), start=date(2040, 1, 2), end=date(2040, 1, 29))

    assert result.window.weeks == 0 and result.questions == [] and result.suppressed


@pytest.mark.parametrize("distinct", [MINIMUM_GROUP - 1, MINIMUM_GROUP])
def test_a_deleted_document_is_never_listed(distinct: int) -> None:
    """V7: only current documents are listed, whatever number of students cited a deleted one."""
    repo = FakeRepository()
    padded(repo)
    for student in students(distinct):
        repo.turn(student, WEEK2, document=None, filename="old-unit.pdf")

    result = get(build(repo))

    assert "old-unit.pdf" not in {d.filename for d in result.documents}
    assert all(d.document_id is not None for d in result.documents)


def test_a_deleted_document_is_not_listed_when_the_whole_subject_is_suppressed() -> None:
    repo = FakeRepository()
    for student in students(MINIMUM_GROUP - 1):
        repo.turn(student, WEEK1, document=None, filename="old-unit.pdf")

    assert "old-unit.pdf" not in {d.filename for d in get(build(repo)).documents}
