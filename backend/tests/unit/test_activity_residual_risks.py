"""Inference risks that remain open by decision of the owner (change `activity-privacy-hardening`).

Characterisations: a **pass means that the risk exists**, not that anything is protected. None of
them is mitigated; they are candidates for a formal acceptance within a restricted institutional
scope, recorded in TD-069. A rule that closes one of them makes its test fail, and then the
register and this module change together. V3 and F6 are characterised in
`test_activity_inference_vectors.py`, F8 in `test_activity_inference_f8.py`.
"""

from datetime import date

from tests.unit.test_activity_original_scope import (
    DOC_A,
    DOC_B,
    DOC_C,
    EARLY,
    LATE,
    Repo,
    cell,
    figure,
    read,
)

OTHER = date(2026, 3, 16)


def test_v6a_the_rates_give_the_size_of_a_withheld_week() -> None:
    repo = Repo()
    for student in range(5):
        repo.ask(student, LATE, 2)
    for student in range(5, 9):  # four students: the cell of this week is withheld
        repo.ask(student, EARLY)
    repo.ask(0, LATE, kind="none")

    result = read(repo)

    assert cell(result, EARLY) is None
    published = sum(p.count for p in result.questions if p.count is not None)
    rate = result.no_material_rate
    totals = [
        total
        for total in range(published, 2 * published)
        if any(round(some / total, 3) == rate for some in range(total + 1))
    ]
    assert [total - published for total in totals] == [4]


def test_v6b_the_uncited_rate_gives_a_withheld_document_figure() -> None:
    repo = Repo({DOC_A: "a.pdf", DOC_B: "b.pdf"})
    for student in range(6):
        repo.ask(student, times=2, docs=(DOC_A,))
    for student in range(4):  # four students: the figure of B is withheld
        repo.ask(student, docs=(DOC_B,))
    for student in range(5):
        repo.ask(student, kind="retrieved")

    result = read(repo)
    total = cell(result, LATE)
    shown = figure(result, DOC_A)
    rate = result.no_cited_source_rate

    assert figure(result, DOC_B) is None
    assert total is not None and shown is not None and rate is not None
    assert total - round(total * rate) - shown == 4  # the cited answers that are not of A


def test_v8_the_cell_total_minus_a_shown_document_bounds_a_withheld_one() -> None:
    repo = Repo({DOC_A: "a.pdf", DOC_B: "b.pdf"})
    for student in range(6):
        repo.ask(student, docs=(DOC_A,))
    for student in range(3):  # three students: the figure of B is withheld
        repo.ask(student, docs=(DOC_B,))

    result = read(repo)
    total, shown = cell(result, LATE), figure(result, DOC_A)

    assert figure(result, DOC_B) is None and total is not None and shown is not None
    assert total - shown == 3  # no rate is needed


def test_v9_the_total_the_no_material_rate_and_a_figure_isolate_one_answer() -> None:
    repo = Repo({DOC_A: "a.pdf", DOC_B: "b.pdf"})
    for student in range(6):
        repo.ask(student, times=2, docs=(DOC_A,))
    for student in range(6):
        repo.ask(student, kind="none")
    repo.ask(0, docs=(DOC_B,))  # the one answer with material that does not cite A

    result = read(repo)
    total, shown = cell(result, LATE), figure(result, DOC_A)
    rate = result.no_material_rate

    assert figure(result, DOC_B) is None
    assert total is not None and shown is not None and rate is not None
    assert total - round(total * rate) - shown == 1


def test_a_rate_of_zero_or_one_speaks_of_every_counted_student() -> None:
    """The class is larger than the counted group, so this is not V12."""
    all_cited, none_with_material = Repo(enrolled=12), Repo(enrolled=12)
    for student in range(6):
        all_cited.ask(student)
        none_with_material.ask(student, kind="none")

    assert read(all_cited).no_material_rate == 0.0  # no counted student ever lacked material
    assert read(none_with_material).no_material_rate == 1.0  # every one of them did


def test_the_enrolled_count_minus_the_active_students_can_be_exactly_one() -> None:
    repo = Repo(enrolled=6)
    for student in range(5):
        repo.ask(student)

    result = read(repo)

    assert result.active_students is not None
    assert result.enrolled_students - result.active_students == 1


def test_v10_with_answers_that_cite_two_documents_a_rate_isolates_the_withheld_ones() -> None:
    repo = Repo({DOC_A: "a.pdf", DOC_B: "b.pdf", DOC_C: "c.pdf"})
    for student in range(6):
        repo.ask(student, docs=(DOC_A, DOC_B))
    for student in range(2):  # two students cite only documents whose figure is withheld
        repo.ask(student, docs=(DOC_C,))

    result = read(repo)
    total = cell(result, LATE)
    assert total is not None and result.no_cited_source_rate == 0.0
    shown = figure(result, DOC_A)
    assert shown is not None

    assert total - shown == 2


def test_v11_the_active_students_and_two_cells_bound_who_asked_in_one_week_only() -> None:
    repo = Repo()
    for student in range(5):
        repo.ask(student, OTHER)
    for student in range(1, 6):
        repo.ask(student, LATE)

    result = read(repo)

    assert (cell(result, OTHER), cell(result, LATE), result.active_students) == (5, 5, 6)
    assert result.active_students is not None
    assert result.active_students - result.minimum_group == 1


def test_v12_when_the_counted_group_is_the_class_one_response_speaks_of_each_student() -> None:
    repo = Repo(enrolled=5)
    for student in range(5):
        repo.ask(student)

    result = read(repo)

    # Five enrolled and five questions from at least five students: each asked exactly one.
    assert (result.enrolled_students, result.active_students, cell(result, LATE)) == (5, 5, 5)
