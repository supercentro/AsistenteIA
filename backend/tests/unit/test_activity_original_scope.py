"""The original scope of the teacher dashboard (change `activity-privacy-hardening`).

The owner decided on 2026-11-26 to keep every planned metric, computed over the requested window
with the original rule (a figure needs 5 distinct students), and to keep one correction: deleted
documents are not listed (V7). The inference risks that follow are characterised in
`test_activity_residual_risks.py`. In memory, fictitious ids, fixed dates.
"""

import random
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from app.repositories.activity_repository import AnswerFact, QuestionFact, SourceFact
from app.schemas.activity import ActivityResponse
from app.services.activity_service import ActivityService

TODAY = date(2026, 3, 30)  # a Monday: the default window is the 12 weeks 01-05 .. 03-29
EARLY = date(2026, 1, 12)  # long before the last two weeks of the window
LATE = date(2026, 3, 23)  # the last ended week
TEACHER, SUBJECT = uuid.uuid4(), uuid.uuid4()
DOC_A, DOC_B, DOC_C = (uuid.UUID(int=n) for n in (1, 2, 3))
PEOPLE = [uuid.UUID(int=100 + n) for n in range(40)]
CITED, PLAIN = "Respuesta ficticia [1].", "Respuesta ficticia sin marcas."


class Repo:
    """The filters of the real repository: half-open window; enrolled students only."""

    def __init__(self, documents: dict[uuid.UUID, str] | None = None, enrolled: int = 40) -> None:
        self.documents = documents if documents is not None else {DOC_A: "a.pdf"}
        self.enrolled = enrolled
        self.asked: list[QuestionFact] = []
        self.answered: list[AnswerFact] = []

    def enrolled_count(self, **_: object) -> int:
        return self.enrolled

    def questions(self, *, start: datetime, end: datetime, **_: object) -> list[QuestionFact]:
        return [q for q in self.asked if start <= q.asked_at < end]

    def answers(self, *, start: datetime, end: datetime, **_: object) -> list[AnswerFact]:
        return [a for a in self.answered if start <= a.answered_at < end]

    def current_documents(self, **_: object) -> list[tuple[uuid.UUID, str]]:
        return sorted(self.documents.items(), key=lambda item: (item[1], str(item[0])))

    def ask(
        self,
        student: int,
        week: date = LATE,
        times: int = 1,
        *,
        docs: tuple[uuid.UUID, ...] = (DOC_A,),
        kind: str = "cited",
    ) -> None:
        when = datetime(week.year, week.month, week.day, 10, tzinfo=UTC) + timedelta(days=1)
        for _ in range(times):
            self.asked.append(QuestionFact(student_id=PEOPLE[student], asked_at=when))
            sources = tuple(
                SourceFact(rank, key, self.documents.get(key, "gone.pdf"))
                for rank, key in enumerate(docs if kind != "none" else (), 1)
            )
            marks = "".join(f"[{s.rank}]" for s in sources) if kind == "cited" else ""
            self.answered.append(AnswerFact(PEOPLE[student], when, f"respuesta {marks}", sources))

    def delete(self, document: uuid.UUID) -> None:
        """What the database does: the chunks go, the sources keep the name and lose the id."""
        self.documents = {k: v for k, v in self.documents.items() if k != document}
        self.answered = [
            AnswerFact(
                a.student_id,
                a.answered_at,
                a.content,
                tuple(
                    SourceFact(
                        s.rank, None if s.document_id == document else s.document_id, s.filename
                    )
                    for s in a.sources
                ),
            )
            for a in self.answered
        ]


def read(repo: Repo, **window: date) -> ActivityResponse:
    subjects = SimpleNamespace(get_for_teacher=lambda *_: SimpleNamespace(last_unenrolment_at=None))
    service = ActivityService(subjects, repo, today=lambda: TODAY)  # type: ignore[arg-type]
    return service.get(TEACHER, SUBJECT, **window)


def figure(result: ActivityResponse, document: uuid.UUID) -> int | None:
    found = {d.document_id: d.cited_appearances for d in result.documents}
    return found[document]


def cell(result: ActivityResponse, week: date) -> int | None:
    return next(p.count for p in result.questions if p.period_start == week)


def test_every_metric_covers_the_whole_requested_window() -> None:
    repo = Repo()
    for student in range(6):
        repo.ask(student, EARLY)
    repo.ask(0, EARLY, kind="none")
    repo.ask(1, EARLY, kind="retrieved")

    result = read(repo)

    assert (result.window.weeks, cell(result, EARLY), result.active_students) == (12, 8, 6)
    assert (result.no_material_rate, result.no_cited_source_rate) == (0.125, 0.25)
    assert figure(result, DOC_A) == 6


def test_the_summary_follows_start_and_end_like_the_weekly_series() -> None:
    repo = Repo()
    for student in range(5):
        repo.ask(student, EARLY)
    for student in range(7):
        repo.ask(student, LATE)

    narrow = read(repo, start=LATE, end=LATE)

    assert (narrow.active_students, figure(narrow, DOC_A)) == (7, 7)
    assert read(repo).active_students == 7 and figure(read(repo), DOC_A) == 12


def test_the_response_has_no_second_period() -> None:
    assert not {"summary_window", "summary_weeks"} & set(read(Repo()).model_dump())


def test_a_rate_is_shown_whatever_the_size_of_its_sides_including_zero() -> None:
    repo = Repo()
    for student in range(5):
        repo.ask(student, times=3)
    assert (read(repo).no_material_rate, read(repo).no_cited_source_rate) == (0.0, 0.0)

    repo.ask(0, kind="none")

    assert (read(repo).no_material_rate, read(repo).no_cited_source_rate) == (0.062, 0.062)


def test_a_figure_one_student_concentrates_is_shown_with_its_true_value() -> None:
    repo = Repo()
    repo.ask(0, times=50)
    for student in range(1, 5):
        repo.ask(student)

    result = read(repo)

    assert (cell(result, LATE), figure(result, DOC_A)) == (54, 54)


def test_a_week_with_a_withheld_cell_still_counts_in_the_summary() -> None:
    repo = Repo()
    for student in range(5):
        repo.ask(student, LATE)
    for student in range(5, 8):
        repo.ask(student, EARLY)

    result = read(repo)

    assert cell(result, EARLY) is None
    assert (result.active_students, figure(result, DOC_A)) == (8, 8)


def test_the_uncited_rate_is_shown_beside_a_withheld_document() -> None:
    repo = Repo({DOC_A: "a.pdf", DOC_B: "b.pdf"})
    for student in range(6):
        repo.ask(student)
    repo.ask(0, docs=(DOC_B,))

    result = read(repo)

    assert figure(result, DOC_B) is None and result.no_cited_source_rate == 0.0


def test_four_active_students_show_only_the_enrolled_count() -> None:
    repo = Repo()
    for student in range(4):
        repo.ask(student, times=3)

    result = read(repo)

    assert result.enrolled_students == 40 and result.suppressed
    assert (result.active_students, result.no_material_rate, result.no_cited_source_rate) == (
        None,
        None,
        None,
    )
    assert all(p.count is None for p in result.questions)
    assert [d.cited_appearances for d in result.documents] == [None]


# --- V7: deleted documents are not listed -------------------------------------------------------


def test_a_deleted_document_is_not_listed_however_many_students_cited_it() -> None:
    repo = Repo({DOC_A: "a.pdf", DOC_B: "b.pdf"})
    for student in range(8):
        repo.ask(student, docs=(DOC_A, DOC_B))

    repo.delete(DOC_B)
    result = read(repo)

    assert [(d.document_id, d.cited_appearances) for d in result.documents] == [(DOC_A, 8)]


def test_two_documents_with_one_name_are_never_added_up_after_deleting_them() -> None:
    repo = Repo({DOC_A: "notes.pdf", DOC_B: "notes.pdf"})
    for student in range(6):
        repo.ask(student, docs=(DOC_A,))
    for student in range(3):
        repo.ask(student, docs=(DOC_B,))
    assert sorted((d.cited_appearances for d in read(repo).documents), key=str) == [6, None]

    repo.delete(DOC_A)
    first = read(repo)
    repo.delete(DOC_B)

    assert [(d.document_id, d.cited_appearances) for d in first.documents] == [(DOC_B, None)]
    assert read(repo).documents == []


def test_successive_deletions_never_change_or_add_a_figure() -> None:
    merging = 0
    for seed in range(120):
        rng = random.Random(seed)  # noqa: S311 - reproducible test data
        keys = [uuid.UUID(int=500 + n) for n in range(4)]
        repo = Repo({key: rng.choice(["notes.pdf", "unit.pdf"]) for key in keys})
        for student in range(rng.randint(5, 9)):
            for _ in range(rng.randint(1, 4)):
                repo.ask(
                    student,
                    docs=(rng.choice(keys),),
                    kind=rng.choice(["cited", "cited", "cited", "retrieved", "none"]),
                )
        names = dict(repo.documents)
        before = read(repo)
        shown = {d.document_id: d.cited_appearances for d in before.documents}
        deleted = rng.sample(keys, rng.randint(2, 4))
        for key in deleted:
            repo.delete(key)
            after = read(repo)
            assert all(d.cited_appearances == shown[d.document_id] for d in after.documents), seed
            assert key not in {d.document_id for d in after.documents}, seed
            assert after.model_dump(exclude={"documents", "suppressed"}) == before.model_dump(
                exclude={"documents", "suppressed"}
            ), seed
        merging += len({names[k] for k in deleted}) < len(deleted)
    assert merging >= 80


def test_answers_alone_never_open_the_summary_when_fewer_than_five_students_asked() -> None:
    """The question of an answer can fall before the window: the askers still decide."""
    repo = Repo()
    for student in range(6):
        repo.ask(student)
    del repo.asked[4:]  # four askers in the window, six students with answers

    result = read(repo)

    assert (result.active_students, result.no_material_rate, result.no_cited_source_rate) == (
        None,
        None,
        None,
    )
    assert figure(result, DOC_A) is None
