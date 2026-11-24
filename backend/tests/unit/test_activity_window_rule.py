"""The window rule of the teacher activity: the unenrolment marker (A2) and ended weeks (A2b).

Change `activity-privacy-hardening` (tasks 3.2a to 3.2d, 3.6). The service runs over an in-memory
repository; the SQL, the transactions and the permissions are in the integration tests. Fictitious
data only.

Two security properties are checked with random worlds and fixed seeds (no property-test
dependency is added):

* **independence from the cut-off past** (V1): two worlds that differ only in messages created
  before the marker in force, written by any student, give identical responses after a removal;
* **temporal independence** (V5): two worlds that differ only in what happens in the open week give
  identical responses (the enrolled count apart).

The control cases run the same worlds without the marker, which stands for the system before A2,
and must differ: a property that cannot fail proves nothing.
"""

# The generators are seeded test data, never a secret: S311 does not apply to this module.
# ruff: noqa: S311

import random
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pytest

from app.core.errors import InvalidActivityWindowError
from app.repositories.activity_repository import AnswerFact, QuestionFact, SourceFact
from app.services.activity_service import MAX_WEEKS, ActivityService, ended_weeks_today
from tests.unit.test_activity_service import (
    CITED,
    DOC_A,
    PLAIN,
    SUBJECT,
    TEACHER,
    FakeRepository,
    FakeSubjects,
)

MONDAY = date(2026, 3, 2)


def utc(day: date, hour: int = 12, minute: int = 0, second: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=UTC)


def service(
    repo: Any, today: date, marker: datetime | None = None, owner: uuid.UUID | None = TEACHER
) -> ActivityService:
    return ActivityService(FakeSubjects(owner, marker), repo, today=lambda: today)  # type: ignore[arg-type]


def read(repo: Any, today: date, marker: datetime | None = None, **window: date) -> Any:
    return service(repo, today, marker).get(TEACHER, SUBJECT, **window)


class WorldRepository:
    """Enrolled students and their messages; the filters of the real repository."""

    def __init__(self) -> None:
        self.enrolled: set[uuid.UUID] = set()
        self.messages: list[tuple[uuid.UUID, datetime, bool]] = []

    def enrolled_count(self, **_: object) -> int:
        return len(self.enrolled)

    def questions(self, *, start: datetime, end: datetime, **_: object) -> list[QuestionFact]:
        return [
            QuestionFact(student_id=student, asked_at=when)
            for student, when, _cited in self.messages
            if student in self.enrolled and start <= when < end
        ]

    def answers(self, *, start: datetime, end: datetime, **_: object) -> list[AnswerFact]:
        found = []
        for student, when, cited in self.messages:
            if student in self.enrolled and start <= when < end:
                sources = (
                    (SourceFact(rank=1, document_id=DOC_A, filename="a.pdf"),) if cited else ()
                )
                content = CITED if cited else PLAIN
                found.append(AnswerFact(student, when, content, sources))
        return found

    def current_documents(self, **_: object) -> list[tuple[uuid.UUID, str]]:
        return [(DOC_A, "a.pdf")]


# --- ended weeks only (A2b) ----------------------------------------------------------------------


def test_the_default_window_is_the_twelve_weeks_that_have_ended() -> None:
    result = read(FakeRepository(), today=date(2026, 3, 4))  # a Wednesday: the open week is 03-02

    assert result.window.end == date(2026, 3, 1)
    assert result.window.start == date(2025, 12, 8)
    assert result.window.weeks == MAX_WEEKS


def test_the_window_moves_by_exactly_one_week_between_sunday_and_monday() -> None:
    sunday = read(FakeRepository(), today=date(2026, 3, 8))
    monday = read(FakeRepository(), today=date(2026, 3, 9))

    assert monday.window.end - sunday.window.end == timedelta(days=7)
    assert monday.window.start - sunday.window.start == timedelta(days=7)
    assert sunday.window.weeks == monday.window.weeks == MAX_WEEKS


def test_an_end_inside_the_open_week_is_clamped_to_the_last_ended_sunday() -> None:
    result = read(
        FakeRepository(), today=date(2026, 3, 4), start=date(2026, 2, 9), end=date(2026, 3, 4)
    )

    assert result.window.end == date(2026, 3, 1)
    assert result.window.weeks == 3


def test_a_start_inside_the_open_week_leaves_no_whole_week() -> None:
    result = read(FakeRepository(), today=date(2026, 3, 4), start=date(2026, 3, 3))

    assert result.window.weeks == 0


def test_the_existing_window_errors_are_kept() -> None:
    repo = FakeRepository()
    with pytest.raises(InvalidActivityWindowError):
        read(repo, today=date(2026, 3, 4), start=date(2026, 3, 1), end=date(2026, 2, 1))
    with pytest.raises(InvalidActivityWindowError):
        read(repo, today=date(2026, 6, 1), start=date(2026, 1, 5), end=date(2026, 5, 31))


# --- the marker of the last unenrolment (A2) ------------------------------------------------------


@pytest.mark.parametrize(
    ("today", "marker", "start", "weeks"),
    [
        (date(2026, 3, 23), utc(date(2026, 3, 4)), date(2026, 3, 9), 2),  # in the middle of a week
        (
            date(2026, 3, 30),
            utc(date(2026, 3, 9), 0),
            date(2026, 3, 16),
            2,
        ),  # a Monday 00:00 exactly
        (date(2026, 3, 23), utc(date(2026, 3, 8), 23, 59, 59), date(2026, 3, 9), 2),  # Sunday night
        (date(2026, 3, 4), utc(date(2025, 10, 1)), date(2025, 12, 8), MAX_WEEKS),  # long ago
        # Sunday 23:30 at UTC-5 is Monday 04:30 UTC: the week of the 9th, so the 16th is first.
        (
            date(2026, 3, 30),
            datetime(2026, 3, 8, 23, 30, tzinfo=timezone(timedelta(hours=-5))),
            date(2026, 3, 16),
            2,
        ),
    ],
    ids=["mid-week", "monday-midnight", "sunday-night", "old", "other-zone"],
)
def test_the_window_starts_after_the_first_monday_following_the_marker(
    today: date, marker: datetime, start: date, weeks: int
) -> None:
    result = read(FakeRepository(), today, marker)

    assert (result.window.start, result.window.weeks) == (start, weeks)


@pytest.mark.parametrize(
    ("today", "marker"),
    [
        (date(2026, 3, 11), utc(date(2026, 3, 10))),  # a removal in the open week
        (date(2026, 3, 16), utc(date(2026, 3, 10))),  # in the last ended week
    ],
    ids=["open-week", "last-ended-week"],
)
def test_no_whole_week_remains_when_the_marker_is_in_the_open_or_the_last_ended_week(
    today: date, marker: datetime
) -> None:
    repo = FakeRepository(enrolled=7)
    result = read(repo, today, marker)

    assert result.window.weeks == 0
    assert result.window.start == result.window.end + timedelta(days=1)
    assert result.questions == []
    assert result.active_students is None
    assert result.no_material_rate is None and result.no_cited_source_rate is None
    assert all(document.cited_appearances is None for document in result.documents)
    assert result.enrolled_students == 7
    assert result.suppressed is True
    assert repo.calls == []  # no question was read at all


def test_a_null_marker_changes_nothing_but_the_ended_weeks_rule() -> None:
    assert read(FakeRepository(), date(2026, 3, 30), None).window.weeks == MAX_WEEKS


def test_the_weeks_before_the_marker_are_not_shown_even_with_data() -> None:
    repo = WorldRepository()  # filters by window like the real repository
    for _ in range(6):
        student = uuid.uuid4()
        repo.enrolled.add(student)
        repo.messages += [(student, utc(MONDAY, 10), True), (student, utc(MONDAY, 11), True)]

    visible = read(repo, date(2026, 3, 30))  # no marker: the week of 03-02 has ended
    hidden = read(repo, date(2026, 3, 30), utc(date(2026, 3, 4)))

    assert next(p.count for p in visible.questions if p.period_start == MONDAY) == 12
    assert MONDAY not in [p.period_start for p in hidden.questions]
    assert hidden.active_students is None


# --- random worlds: the two security properties -----------------------------------------------


DAY0 = date(2026, 1, 5)  # a Monday


def day(index: int) -> date:
    return DAY0 + timedelta(days=index)


def build_world(seed: int, variant: int, only_removed: bool) -> tuple[WorldRepository, Any]:
    """Two worlds of the same seed that differ only before the removal (`variant` 1 or 2)."""
    common = random.Random(seed)
    people = [uuid.UUID(int=seed * 100 + number + 1) for number in range(common.randint(6, 9))]
    removed = people[common.randrange(len(people))]
    removal_day = common.randint(60, 100)
    reenrol_day = removal_day + common.randint(1, 20) if common.random() < 0.5 else None
    differing = random.Random(seed * 31 + variant)
    repo = WorldRepository()
    repo.enrolled = set(people)
    for index in range(130):
        for student in people:
            stream = random.Random(f"{seed}:{index}:{student}")
            if index < removal_day:
                differs = student == removed if only_removed else True
                source = differing if differs else stream
            else:
                if student == removed and not (reenrol_day is not None and index >= reenrol_day):
                    continue
                source = stream
            for slot in range(source.choice([0, 0, 1, 2, 3])):
                repo.messages.append((student, utc(day(index), 10 + slot), source.random() < 0.6))
    return repo, SimpleRemoval(removed, removal_day, reenrol_day)


class SimpleRemoval:
    def __init__(self, student: uuid.UUID, removal_day: int, reenrol_day: int | None) -> None:
        self.student, self.removal_day, self.reenrol_day = student, removal_day, reenrol_day


def reads_after_the_removal(seed: int, variant: int, only_removed: bool, marked: bool) -> list[Any]:
    repo, removal = build_world(seed, variant, only_removed)
    marker = utc(day(removal.removal_day)) if marked else None
    repo.enrolled.discard(removal.student)
    answers = []
    for index in range(removal.removal_day, 130, 3):
        if removal.reenrol_day is not None and index >= removal.reenrol_day:
            repo.enrolled.add(removal.student)
        answers.append(read(repo, day(index), marker).model_dump(mode="json"))
    return answers


SEEDS = range(25)


@pytest.mark.parametrize("seed", SEEDS)
def test_a_read_after_a_removal_does_not_depend_on_anything_before_the_marker(seed: int) -> None:
    assert reads_after_the_removal(seed, 1, False, True) == reads_after_the_removal(
        seed, 2, False, True
    )


@pytest.mark.parametrize("seed", SEEDS)
def test_the_same_worlds_differ_without_the_marker(seed: int) -> None:
    """Control: the property can fail. Without the marker the weeks the removal hides come back."""
    assert reads_after_the_removal(seed, 1, False, False) != reads_after_the_removal(
        seed, 2, False, False
    )


def test_the_weaker_formulation_holds_without_any_mitigation_unless_there_is_a_re_enrolment() -> (
    None
):
    """Why the property above covers every student: worlds that differ only in the removed
    student's messages already give equal answers while the student stays removed."""
    plain, reenrolled = 0, 0
    for seed in SEEDS:
        _repo, removal = build_world(seed, 1, True)
        equal = reads_after_the_removal(seed, 1, True, False) == reads_after_the_removal(
            seed, 2, True, False
        )
        if removal.reenrol_day is None:
            assert equal
            plain += 1
        else:
            assert not equal
            reenrolled += 1
    assert plain > 0 and reenrolled > 0


@pytest.mark.parametrize("seed", SEEDS)
def test_a_read_does_not_depend_on_what_happens_in_the_open_week(seed: int) -> None:
    """V5: two worlds that differ in the open week, including a student enrolled in it."""
    answers = []
    for variant in (1, 2):
        common = random.Random(seed)
        people = [uuid.UUID(int=seed * 100 + number + 1) for number in range(7)]
        newcomer = uuid.UUID(int=seed * 100 + 99)
        repo = WorldRepository()
        repo.enrolled = set(people)
        week_start = common.randint(30, 90) // 7 * 7
        for index in range(week_start):  # the ended weeks: the same in both worlds
            for student in people:
                stream = random.Random(f"{seed}:{index}:{student}")
                for slot in range(stream.choice([0, 1, 2])):
                    repo.messages.append(
                        (student, utc(day(index), 10 + slot), stream.random() < 0.6)
                    )
        today = week_start + random.Random(seed).randint(1, 6)
        open_week = random.Random(seed * 17 + variant)
        if variant == 2:
            repo.enrolled.add(newcomer)
        for index in range(week_start, today + 1):
            for student in [*people, newcomer] if variant == 2 else people:
                for slot in range(open_week.choice([0, 1, 2])):
                    repo.messages.append(
                        (student, utc(day(index), 8 + slot), open_week.random() < 0.6)
                    )
        response = read(repo, day(today)).model_dump(mode="json")
        response.pop("enrolled_students")
        answers.append(response)
    assert answers[0] == answers[1]


def test_two_reads_in_one_week_are_identical_although_a_question_arrived() -> None:
    repo = WorldRepository()
    people = [uuid.uuid4() for _ in range(5)]
    repo.enrolled = set(people)
    for student in people:
        repo.messages += [(student, utc(MONDAY, 10), True), (student, utc(MONDAY, 11), True)]
    wednesday = MONDAY + timedelta(days=2)  # inside the open week of 03-02

    first = read(repo, wednesday).model_dump(mode="json")
    repo.messages.append((people[2], utc(wednesday, 14), True))
    second = read(repo, wednesday).model_dump(mode="json")

    assert first == second


# --- a week counts as ended one hour after its Sunday (review finding m-1) ------------------------


@pytest.mark.parametrize(
    ("now", "day"),
    [
        (datetime(2026, 3, 9, 0, 0, 0, tzinfo=UTC), date(2026, 3, 8)),  # Monday 00:00: still Sunday
        (datetime(2026, 3, 9, 0, 59, 59, tzinfo=UTC), date(2026, 3, 8)),
        (datetime(2026, 3, 9, 1, 0, 0, tzinfo=UTC), date(2026, 3, 9)),  # one hour later: Monday
        (datetime(2026, 3, 8, 23, 59, 59, tzinfo=UTC), date(2026, 3, 8)),
        # 01:30 on Monday at UTC+2 is Sunday 23:30 UTC: the same instant, measured in UTC
        (datetime(2026, 3, 9, 1, 30, tzinfo=timezone(timedelta(hours=2))), date(2026, 3, 8)),
    ],
    ids=["midnight", "last-second", "one-hour", "sunday", "other-zone"],
)
def test_a_week_counts_as_ended_one_hour_after_its_sunday(now: datetime, day: date) -> None:
    assert ended_weeks_today(now) == day


def test_the_default_clock_has_the_same_margin() -> None:
    sunday = read(FakeRepository(), ended_weeks_today(datetime(2026, 3, 9, 0, 30, tzinfo=UTC)))
    monday = read(FakeRepository(), ended_weeks_today(datetime(2026, 3, 9, 1, 30, tzinfo=UTC)))

    assert monday.window.end - sunday.window.end == timedelta(days=7)
