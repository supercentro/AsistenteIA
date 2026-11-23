"""Demonstration of the individual-inference vectors of the aggregate teacher activity.

Change `activity-privacy-hardening`, part A (tasks 1.1 to 1.4). **No mitigation is implemented.**
Fictitious data and the in-memory repository only: nothing here reads or writes a database.

Two kinds of test, so that the suite stays green while the vectors stay open:

* ``test_v*_is_reproduced``: asserts the leak. **PASS means the vulnerability is confirmed at the
  service level**, not that the system is safe.
* ``test_v*_property_holds``: asserts the property a mitigation must give, marked
  ``xfail(strict=True)``. It fails today (the TDD failing run); the day a mitigation makes it
  pass, strict mode turns the pass into an error so that the marker, and the entry of TD-069, are
  reviewed. The mitigation is *accepted* only when this test passes unchanged (spec requirement).

Limits of the evidence: the in-memory repository reproduces the filters of the real one
(enrolled only, window) by construction, so it shows the **arithmetic** of the service, not that
the surrounding flow allows each step (the end-to-end check of V2 is in
`tests/integration/test_activity_inference_f8.py`). The erasure invariant needs a database
and is in that same integration module.
"""

import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import pytest

from app.repositories.activity_repository import AnswerFact, QuestionFact
from app.services.activity_service import MINIMUM_GROUP, ActivityService
from tests.unit.test_activity_service import (
    PLAIN,
    SUBJECT,
    TEACHER,
    FakeRepository,
    FakeSubjects,
)

WEEK1 = date(2026, 3, 2)  # a Monday
FOUR_WEEKS = {"start": WEEK1, "end": date(2026, 3, 29)}
TWELVE_WEEKS = {"start": WEEK1, "end": date(2026, 5, 24)}
TWELVE_WEEKS_LATER = {"start": WEEK1 + timedelta(days=7), "end": date(2026, 5, 31)}
TODAY = date(2026, 6, 1)


class WindowedRepository(FakeRepository):
    """The in-memory repository, filtering by the window like the SQL one does."""

    def questions(
        self, *, teacher_id: Any, subject_id: Any, start: Any, end: Any
    ) -> list[QuestionFact]:
        return [q for q in self.question_facts if start <= q.asked_at < end]

    def answers(
        self, *, teacher_id: Any, subject_id: Any, start: Any, end: Any
    ) -> list[AnswerFact]:
        return [a for a in self.answer_facts if start <= a.answered_at < end]


def service(repo: FakeRepository) -> ActivityService:
    return ActivityService(FakeSubjects(TEACHER), repo, today=lambda: TODAY)  # type: ignore[arg-type]


def read(repo: FakeRepository, window: dict[str, date]) -> Any:
    return service(repo).get(TEACHER, SUBJECT, **window)


def class_of(
    contributions: Sequence[int], week: date = WEEK1
) -> tuple[WindowedRepository, list[uuid.UUID]]:
    """One student per figure of `contributions`, each asking that many questions in `week`."""
    repo = WindowedRepository(enrolled=len(contributions))
    members = [uuid.uuid4() for _ in contributions]
    for student, count in zip(members, contributions, strict=True):
        for _ in range(count):
            repo.turn(student, week)
    return repo, members


def shown(result: Any, week: date) -> int:
    """The cell of a week that must be shown."""
    value = week_cell(result, week)
    assert value is not None
    return value


def week_cell(result: Any, week: date) -> int | None:
    count: int | None = next(p.count for p in result.questions if p.period_start == week)
    return count


# --- V1: unenrolment differencing (F1, task 1.1) ---------------------------------------------

V1_CLASS = [2, 2, 2, 2, 2, 3]  # six students; the last one asked 3 questions


def v1_reads() -> tuple[Any, Any]:
    before, _ = class_of(V1_CLASS)
    after, _ = class_of(V1_CLASS[:-1])  # the teacher removed the last student from the enrolments
    return read(before, FOUR_WEEKS), read(after, FOUR_WEEKS)


def test_v1_is_reproduced_the_difference_of_two_reads_is_one_students_contribution() -> None:
    first, second = v1_reads()

    assert (week_cell(first, WEEK1), first.active_students) == (13, 6)
    assert (week_cell(second, WEEK1), second.active_students) == (10, 5)
    assert shown(first, WEEK1) - shown(second, WEEK1) == V1_CLASS[-1]  # exactly 3


def test_v1_does_not_leak_below_the_group_size() -> None:
    """Control case: a class of exactly N shows nothing once one student is removed."""
    before, _ = class_of([2] * MINIMUM_GROUP)
    after, _ = class_of([2] * (MINIMUM_GROUP - 1))

    assert week_cell(read(before, FOUR_WEEKS), WEEK1) == 2 * MINIMUM_GROUP
    assert week_cell(read(after, FOUR_WEEKS), WEEK1) is None


@pytest.mark.xfail(
    strict=True, reason="V1/F1 open: TD-069; passes only with a mitigation of the cause"
)
def test_v1_property_holds_the_removal_of_one_student_does_not_reveal_their_contribution() -> None:
    first, second = v1_reads()

    assert shown(first, WEEK1) - shown(second, WEEK1) != V1_CLASS[-1]


# --- V2: padding with controlled accounts (F8, task 1.2) -------------------------------------

CONTROLLED_QUESTIONS = 4 * 3  # four accounts the teacher controls, 3 questions each


def v2_read(real_questions: int) -> Any:
    repo = WindowedRepository(enrolled=5)
    for _ in range(4):
        controlled = uuid.uuid4()
        for _ in range(3):
            repo.turn(controlled, WEEK1)
    real = uuid.uuid4()
    for _ in range(real_questions):
        repo.turn(real, WEEK1)
    return read(repo, FOUR_WEEKS)


def test_v2_is_reproduced_at_service_level_the_teacher_subtracts_what_it_produced() -> None:
    result = v2_read(real_questions=2)

    assert (week_cell(result, WEEK1), result.active_students) == (14, 5)
    assert shown(result, WEEK1) - CONTROLLED_QUESTIONS == 2  # the real student, recovered


def test_v2_is_reproduced_at_service_level_the_presence_of_a_figure_reveals_activity() -> None:
    silent = v2_read(real_questions=0)

    assert silent.active_students is None  # four active students: everything withheld
    assert week_cell(silent, WEEK1) is None
    assert v2_read(real_questions=1).active_students == 5  # one question is enough to show it


@pytest.mark.xfail(
    strict=True,
    reason="V2/F8 open (feasibility: see the end-to-end test); needs an identity control",
)
def test_v2_property_holds_the_real_students_activity_is_not_recoverable() -> None:
    result = v2_read(real_questions=2)
    silent = v2_read(real_questions=0)

    assert shown(result, WEEK1) - CONTROLLED_QUESTIONS != 2
    assert (silent.active_students is None) == (result.active_students is None)


# --- V3: window differencing (task 1.3) ------------------------------------------------------


def v3_repo() -> WindowedRepository:
    """Five regular students ask once a week for 13 weeks and cite a document. A sixth student asked
    once, in week 1 only, and got an answer without material."""
    repo = WindowedRepository(enrolled=6)
    regular = [uuid.uuid4() for _ in range(5)]
    for index in range(13):
        for student in regular:
            repo.turn(student, WEEK1 + timedelta(days=7 * index))
    repo.turn(uuid.uuid4(), WEEK1, content=PLAIN, with_sources=False)
    return repo


def test_v3_is_reproduced_two_windows_that_differ_by_one_week_leak_window_wide_figures() -> None:
    repo = v3_repo()
    first, second = read(repo, TWELVE_WEEKS), read(repo, TWELVE_WEEKS_LATER)

    assert (first.active_students, second.active_students) == (6, 5)  # the sixth student left
    assert first.no_material_rate == pytest.approx(1 / 61, abs=1e-3)
    assert second.no_material_rate == 0.0  # so the week that left held an answer without material


def test_v3_the_weekly_cells_do_not_move_between_the_two_windows() -> None:
    """What the design already protects: a cell of a week both windows contain is identical."""
    repo = v3_repo()
    first, second = read(repo, TWELVE_WEEKS), read(repo, TWELVE_WEEKS_LATER)

    for index in range(1, 12):
        week = WEEK1 + timedelta(days=7 * index)
        assert week_cell(first, week) == week_cell(second, week) == 5
    assert week_cell(first, WEEK1) == 6  # the week that left shows the sixth student


@pytest.mark.xfail(
    strict=True, reason="V3 open: TD-069; window-wide figures move by the weeks that leave"
)
def test_v3_property_holds_moving_the_window_does_not_reveal_a_students_activity() -> None:
    repo = v3_repo()
    first, second = read(repo, TWELVE_WEEKS), read(repo, TWELVE_WEEKS_LATER)

    assert first.active_students == second.active_students
    assert first.no_material_rate == second.no_material_rate


# --- V4: a heavy contributor (F6, task 1.4), a characterisation, not a recovery --------------


def test_v4_characterisation_one_student_can_be_most_of_a_shown_figure() -> None:
    repo, members = class_of([50, 1, 1, 1, 1])
    result = read(repo, FOUR_WEEKS)

    cell = week_cell(result, WEEK1)
    assert cell == 54  # shown: five distinct students
    assert 50 / cell > 0.9  # one student is 93 % of it; the teacher cannot tell which one from this
    assert len(members) == MINIMUM_GROUP
