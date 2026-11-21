"""Retrieval, refusal and isolation metrics on hand-made rankings (task 1.2 and 1.6)."""

import uuid

from app.repositories.chunk_repository import ScoredChunk
from tests.evaluation.cases import Case, Expected, ExpectedSource, HistoryMessage
from tests.evaluation.metrics import (
    Retrieved,
    isolation_violations,
    retrieval_rows,
    supports,
)


def chunk(filename: str, content: str, similarity: float) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_filename=filename,
        chunk_index=0,
        page_number=None,
        content=content,
        similarity=similarity,
    )


def sources(filename: str = "a.md", passage: str = "alfa") -> Expected:
    return Expected(
        type="sources", sources=[ExpectedSource(filename=filename, passage_contains=passage)]
    )


def case(
    case_id: str, kind: str = "answerable", expected: Expected | None = None, **more: object
) -> Case:
    values: dict[str, object] = {
        "id": case_id,
        "kind": kind,
        "subject": "s1",
        "question": "pregunta",
        "expected": expected or sources(),
    }
    values.update(more)
    return Case.model_validate(values)


GOOD = chunk("a.md", "texto con ALFA dentro", 0.9)
OTHER = chunk("b.md", "nada que ver", 0.8)


def row_for(cases: list[Case], outcomes: dict[str, Retrieved], top_k: int, threshold: float):  # type: ignore[no-untyped-def]
    rows = retrieval_rows(
        cases, outcomes, top_ks=[top_k], thresholds=[threshold], default=(top_k, threshold)
    )
    return rows[0]


def test_supports_matches_filename_and_passage_ignoring_case_and_whitespace() -> None:
    expected = sources("a.md", "alfa  beta").sources

    assert supports(chunk("a.md", "x Alfa\nBeta y", 0.5), expected)
    assert not supports(chunk("b.md", "x alfa beta y", 0.5), expected)
    assert not supports(chunk("a.md", "x alfa gamma y", 0.5), expected)


def test_supports_checks_the_page_when_the_case_names_one() -> None:
    expected = [ExpectedSource(filename="a.md", passage_contains="alfa", page=3)]
    on_page = ScoredChunk(uuid.uuid4(), uuid.uuid4(), "a.md", 0, 3, "alfa", 0.5)
    elsewhere = ScoredChunk(uuid.uuid4(), uuid.uuid4(), "a.md", 0, 4, "alfa", 0.5)

    assert supports(on_page, expected)
    assert not supports(elsewhere, expected)


def test_hit_at_k_and_mrr_follow_the_rank_of_the_first_supporting_chunk() -> None:
    cases = [case("c1"), case("c2"), case("c3")]
    outcomes = {
        "c1": Retrieved(chunks=(GOOD, OTHER)),  # rank 1
        "c2": Retrieved(chunks=(OTHER, GOOD)),  # rank 2
        "c3": Retrieved(chunks=(OTHER, OTHER, OTHER, GOOD)),  # rank 4
    }

    row = row_for(cases, outcomes, top_k=5, threshold=0.0)

    assert row.answerable.n == 3
    assert row.answerable.hit1 == 1 / 3
    assert row.answerable.hit3 == 2 / 3
    assert row.answerable.hit5 == 1.0
    assert row.answerable.mrr == (1 + 1 / 2 + 1 / 4) / 3


def test_top_k_truncates_the_ranking() -> None:
    cases = [case("c1")]
    outcomes = {"c1": Retrieved(chunks=(OTHER, OTHER, GOOD))}

    assert row_for(cases, outcomes, top_k=2, threshold=0.0).answerable.supported == 0.0
    assert row_for(cases, outcomes, top_k=3, threshold=0.0).answerable.supported == 1.0


def test_a_threshold_above_every_similarity_refuses_the_answerable_case() -> None:
    cases = [case("c1")]
    outcomes = {"c1": Retrieved(chunks=(chunk("a.md", "alfa", 0.2),))}

    row = row_for(cases, outcomes, top_k=5, threshold=0.3)

    assert row.answerable.refused == 1.0
    assert row.answerable.supported == 0.0


def test_unanswerable_cases_that_pass_the_threshold_are_counted() -> None:
    cases = [
        case("u1", "unanswerable", Expected(type="no_material")),
        case("u2", "unanswerable", Expected(type="no_material")),
    ]
    outcomes = {
        "u1": Retrieved(chunks=(chunk("a.md", "algo", 0.5),)),
        "u2": Retrieved(chunks=(chunk("a.md", "algo", 0.1),)),
    }

    row = row_for(cases, outcomes, top_k=5, threshold=0.3)

    assert row.unanswerable_total == 2
    assert row.unanswerable_passed == 0.5


def test_follow_ups_are_reported_apart_from_self_contained_questions() -> None:
    history = [HistoryMessage(role="user", content="hola")]
    cases = [case("c1"), case("f1", "follow_up", history=history)]
    outcomes = {"c1": Retrieved(chunks=(GOOD,)), "f1": Retrieved(chunks=(OTHER,))}

    row = row_for(cases, outcomes, top_k=5, threshold=0.0)

    assert row.answerable.supported == 1.0
    assert row.follow_up.n == 1 and row.follow_up.supported == 0.0


def test_the_sweep_has_one_row_per_combination_and_marks_the_default() -> None:
    cases = [case("c1")]
    outcomes = {"c1": Retrieved(chunks=(GOOD,))}

    rows = retrieval_rows(
        cases, outcomes, top_ks=[3, 5], thresholds=[0.2, 0.3, 0.4], default=(5, 0.3)
    )

    assert len(rows) == 6
    assert [(r.top_k, r.threshold) for r in rows if r.default] == [(5, 0.3)]


def test_empty_groups_report_zero_without_dividing_by_zero() -> None:
    row = row_for([case("c1")], {"c1": Retrieved(chunks=(GOOD,))}, top_k=5, threshold=0.0)

    assert row.follow_up.n == 0 and row.follow_up.mrr == 0.0
    assert row.unanswerable_total == 0 and row.unanswerable_passed == 0.0


def test_isolation_flags_a_chunk_of_another_subject() -> None:
    cases = [case("x1", "cross_subject", Expected(type="isolation"))]
    outcomes = {"x1": Retrieved(chunks=(chunk("de-otra-materia.md", "alfa", 0.9),))}

    violations = isolation_violations(cases, outcomes, {"a.md": "s1", "de-otra-materia.md": "s2"})

    assert violations == ["x1"]


def test_isolation_accepts_chunks_of_the_same_subject() -> None:
    cases = [case("x1", "cross_subject", Expected(type="isolation"))]
    outcomes = {"x1": Retrieved(chunks=(GOOD,))}

    assert isolation_violations(cases, outcomes, {"a.md": "s1"}) == []


def test_a_not_enrolled_student_must_be_denied() -> None:
    cases = [case("n1", "not_enrolled", Expected(type="denied"), student="not_enrolled")]

    assert isolation_violations(cases, {"n1": Retrieved(chunks=(GOOD,))}, {"a.md": "s1"}) == ["n1"]
    assert isolation_violations(cases, {"n1": Retrieved(denied=True)}, {"a.md": "s1"}) == []
