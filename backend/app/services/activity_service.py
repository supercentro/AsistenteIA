"""Aggregate activity of a subject for its owning teacher (change `activity-events-and-metrics`).

Rules, all approved by the owner on 2026-11-23:

* aggregate only: counts, rates and document names; never text, identifiers or per-student figures;
* a figure that comes from fewer than ``MINIMUM_GROUP`` distinct students is withheld (``None``),
  including a figure with no student at all, so that a withheld cell never tells "one to four"
  from "none"; a subject with fewer active students shows only the enrolled count;
* fixed weekly buckets (Monday to Sunday, UTC) and a window of whole weeks, at most
  ``MAX_WEEKS`` of them (84 days, within the 90-day limit), so that shifting the window by days
  cannot move a weekly cell (the window-wide totals still differ between windows that differ by
  whole weeks, and the teacher controls enrolment: both are residual risks, TD-069);
* only students currently enrolled, and only what exists when the request is made; nothing is
  stored, so a deletion lowers the next result;
* only weeks that have ended (A2b, change `activity-privacy-hardening`): the open week is never
  shown, so two reads in the same week are identical and the first questions of a newly enrolled
  student cannot be seen as they happen;
* only weeks that start after the last unenrolment (A2): the subject keeps the moment of its last
  unenrolment and no figure covers a week that starts before it. A student who was removed can only
  have asked before that moment, so a read made after a removal never covers the weeks that held
  the student, and cannot be subtracted from a read made before it.
"""

import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from app.core.errors import InvalidActivityWindowError, NotFoundError
from app.repositories.activity_repository import ActivityRepository, AnswerFact
from app.repositories.subject_repository import SubjectRepository
from app.schemas.activity import (
    ActivityDocument,
    ActivityPeriod,
    ActivityResponse,
    ActivityWindow,
)
from app.services.prompt_builder import attribution_of
from app.services.subject_service import SUBJECT_NOT_FOUND_MESSAGE

MINIMUM_GROUP = 5
MAX_WEEKS = 12
RATE_DIGITS = 3
DocumentKey = uuid.UUID | str  # the id of the document, or its stored name once it was deleted


ENDED_GRACE = timedelta(hours=1)


def ended_weeks_today(now: datetime) -> date:
    """The day the window is measured from: a week counts as ended one hour after its Sunday.

    A chat transaction that began before Monday 00:00 UTC keeps `created_at` in the week that
    ends (the column is the start of the transaction) and can commit a little later, so a read
    made at once after midnight and one made later could differ by that message. The margin
    covers the longest transaction of a chat turn (the lock is never held while the model runs).
    """
    return (now - ENDED_GRACE).astimezone(UTC).date()


def _utc_today() -> date:
    return ended_weeks_today(datetime.now(UTC))


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _after_marker(first: date, marker: datetime | None) -> date:
    """The first week that starts after the first Monday that follows the unenrolment marker.

    A marker exactly on a Monday 00:00 still hides that Monday's week, so the proof does not
    depend on two timestamps being equal.
    """
    if marker is None:
        return first
    return max(first, _monday(marker.astimezone(UTC).date()) + timedelta(days=7))


def _shown(students: set[uuid.UUID], figure: int) -> int | None:
    return figure if len(students) >= MINIMUM_GROUP else None


class ActivityService:
    def __init__(
        self,
        subjects: SubjectRepository,
        activity: ActivityRepository,
        *,
        today: Callable[[], date] = _utc_today,
    ) -> None:
        self._subjects = subjects
        self._activity = activity
        self._today = today

    def get(
        self,
        teacher_id: uuid.UUID,
        subject_id: uuid.UUID,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> ActivityResponse:
        subject = self._subjects.get_for_teacher(subject_id, teacher_id)
        if subject is None:
            raise NotFoundError(SUBJECT_NOT_FOUND_MESSAGE)  # same answer as an unknown subject
        try:
            first, last = self._window(start, end)
            first = _after_marker(first, subject.last_unenrolment_at)
            weeks = max(0, ((last - first).days + 1) // 7)
            since = datetime(first.year, first.month, first.day, tzinfo=UTC)
            until = since + timedelta(days=7 * weeks)  # exclusive
        except OverflowError as error:  # dates next to the calendar limits
            raise InvalidActivityWindowError(
                "out_of_range", "The window is out of range"
            ) from error
        scope = {"teacher_id": teacher_id, "subject_id": subject_id}
        enrolled = self._activity.enrolled_count(**scope)
        if weeks == 0:  # nothing may be shown: no fact is read at all
            return self._no_weeks(last, enrolled, self._activity.current_documents(**scope))
        asked = self._activity.questions(**scope, start=since, end=until)
        answered = self._activity.answers(**scope, start=since, end=until)
        current = self._activity.current_documents(**scope)

        per_week: dict[date, list[uuid.UUID]] = defaultdict(list)
        for question in asked:
            week = _monday(question.asked_at.astimezone(UTC).date())
            if first <= week <= _monday(last):
                per_week[week].append(question.student_id)
        active = {question.student_id for question in asked}
        subject_shown = len(active) >= MINIMUM_GROUP

        periods = []
        for index in range(weeks):
            week = first + timedelta(days=7 * index)
            members = per_week.get(week, [])
            count = _shown(set(members), len(members)) if subject_shown else None
            periods.append(ActivityPeriod(period_start=week, count=count))

        no_material, no_cited = self._rates(answered) if subject_shown else (None, None)
        documents = self._documents(answered, current, subject_shown)
        response = ActivityResponse(
            window=ActivityWindow(start=first, end=last, granularity="week", weeks=weeks),
            minimum_group=MINIMUM_GROUP,
            enrolled_students=enrolled,
            active_students=len(active) if subject_shown else None,
            questions=periods,
            no_material_rate=no_material,
            no_cited_source_rate=no_cited,
            documents=documents,
            suppressed=False,
        )
        response.suppressed = _anything_withheld(response)
        return response

    def _window(self, start: date | None, end: date | None) -> tuple[date, date]:
        """The requested days widened to whole weeks and cut at the last week that has ended.

        Refuses a reversed or too long window. The result may hold no week (the start is inside the
        open week): the caller measures it.
        """
        requested_end = end if end is not None else self._today()
        if start is not None and requested_end < start:
            raise InvalidActivityWindowError("end_before_start", "The end is before the start")
        last_ended_sunday = _monday(self._today()) - timedelta(days=1)  # A2b: the open week is out
        last_day = min(requested_end, last_ended_sunday)
        if start is None:
            first = _monday(last_day) - timedelta(days=7 * (MAX_WEEKS - 1))
        else:
            first = _monday(start)
        last = _monday(last_day) + timedelta(days=6)
        if ((last - first).days + 1) // 7 > MAX_WEEKS:
            raise InvalidActivityWindowError(
                "window_too_long", f"The window covers at most {MAX_WEEKS} weeks"
            )
        return first, last

    def _no_weeks(
        self, last: date, enrolled: int, current: list[tuple[uuid.UUID, str]]
    ) -> ActivityResponse:
        """No whole week may be shown: only the enrolled count and the names of the documents."""
        response = ActivityResponse(
            window=ActivityWindow(
                start=last + timedelta(days=1), end=last, granularity="week", weeks=0
            ),
            minimum_group=MINIMUM_GROUP,
            enrolled_students=enrolled,
            active_students=None,
            questions=[],
            no_material_rate=None,
            no_cited_source_rate=None,
            documents=self._documents([], current, False),
            suppressed=True,
        )
        return response

    @staticmethod
    def _rates(answers: list[AnswerFact]) -> tuple[float | None, float | None]:
        """No-material and no-cited-source shares; null below the minimum group of students."""
        students = {answer.student_id for answer in answers}
        if len(students) < MINIMUM_GROUP:
            return None, None
        without_material = sum(1 for answer in answers if not answer.sources)
        not_cited = sum(1 for answer in answers if _attribution(answer) != "cited")
        total = len(answers)
        return (
            round(without_material / total, RATE_DIGITS),
            round(not_cited / total, RATE_DIGITS),
        )

    @staticmethod
    def _documents(
        answers: list[AnswerFact], current: list[tuple[uuid.UUID, str]], subject_shown: bool
    ) -> list[ActivityDocument]:
        """Answers that cite each document, once per answer, and the students behind each figure."""
        names: dict[DocumentKey, str] = dict(current)
        appearances: dict[DocumentKey, int] = defaultdict(int)
        students: dict[DocumentKey, set[uuid.UUID]] = defaultdict(set)
        for answer in answers:
            if _attribution(answer) != "cited":
                continue
            cited = {
                (source.document_id or source.filename): source.filename
                for source in answer.sources
            }
            for key, filename in cited.items():
                appearances[key] += 1
                students[key] |= {answer.student_id}
                names.setdefault(key, filename)  # a deleted document keeps the stored file name
        # A deleted document is listed only when its figure is shown: its presence alone would tell
        # that at least one student cited it.
        ordered = sorted(
            (
                (key, filename)
                for key, filename in names.items()
                if isinstance(key, uuid.UUID)
                or (subject_shown and len(students[key]) >= MINIMUM_GROUP)
            ),
            key=lambda item: (item[1], str(item[0])),
        )
        return [
            ActivityDocument(
                document_id=key if isinstance(key, uuid.UUID) else None,
                filename=filename,
                cited_appearances=(
                    _shown(students[key], appearances[key]) if subject_shown else None
                ),
            )
            for key, filename in ordered
        ]


def _attribution(answer: AnswerFact) -> str | None:
    return attribution_of(answer.content, [source.rank for source in answer.sources])


def _anything_withheld(response: ActivityResponse) -> bool:
    figures: list[object] = [
        response.active_students,
        response.no_material_rate,
        response.no_cited_source_rate,
        *(period.count for period in response.questions),
        *(document.cited_appearances for document in response.documents),
    ]
    return any(figure is None for figure in figures)
