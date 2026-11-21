"""Attribution classification of answers with the production citation selection (task 1.3, 1.4)."""

import uuid

from app.repositories.chunk_repository import ScoredChunk
from app.services import prompt_builder
from tests.evaluation import attribution
from tests.evaluation.attribution import attribution_summary, classify_answer
from tests.evaluation.cases import Case, Expected, ExpectedSource, HistoryMessage


def chunk(filename: str, content: str) -> ScoredChunk:
    return ScoredChunk(uuid.uuid4(), uuid.uuid4(), filename, 0, None, content, 0.9)


CHUNKS = [
    chunk("a.md", "el dato alfa esta aqui"),
    chunk("b.md", "algo que no sirve"),
    chunk("a.md", "otro dato beta"),
]


def make_case(case_id: str = "c1", kind: str = "answerable", **more: object) -> Case:
    values: dict[str, object] = {
        "id": case_id,
        "kind": kind,
        "subject": "s1",
        "question": "pregunta",
        "model": True,
        "expected": Expected(
            type="sources", sources=[ExpectedSource(filename="a.md", passage_contains="dato alfa")]
        ),
    }
    values.update(more)
    return Case.model_validate(values)


def test_the_classifier_uses_the_production_citation_selection() -> None:
    assert vars(attribution)["select_cited"] is prompt_builder.select_cited


def test_a_valid_marker_on_a_supporting_chunk_is_a_supported_citation() -> None:
    result = classify_answer(make_case(), "Es alfa [1].", CHUNKS)

    assert not result.fallback
    assert result.cited == (1,)
    assert result.supporting is True
    assert result.unsupported is False


def test_an_answer_without_a_valid_marker_is_a_fallback_to_all_chunks() -> None:
    result = classify_answer(make_case(), "Es alfa, sin marcas.", CHUNKS)

    assert result.fallback is True
    assert result.cited == (1, 2, 3)  # what the endpoint would store as sources
    assert result.supporting is False
    assert result.unsupported is False  # no marker was chosen by the model: not a wrong citation


def test_a_marker_out_of_range_does_not_count_and_falls_back() -> None:
    result = classify_answer(make_case(), "Es alfa [7].", CHUNKS)

    assert result.fallback is True
    assert result.markers == ()


def test_a_marker_on_a_chunk_without_the_accepted_passage_is_a_wrong_citation() -> None:
    result = classify_answer(make_case(), "Es alfa [2].", CHUNKS)

    assert not result.fallback
    assert result.cited == (2,)
    assert result.supporting is False
    assert result.unsupported is True


def test_one_good_and_one_bad_marker_is_supported_and_also_unsupported() -> None:
    result = classify_answer(make_case(), "Es alfa [1] y beta [2].", CHUNKS)

    assert result.supporting is True
    assert result.unsupported is True


def test_a_stale_marker_replayed_from_the_history_is_a_wrong_citation_in_a_follow_up() -> None:
    case = make_case(
        "f1",
        "trap_history_marker",
        history=[
            HistoryMessage(role="user", content="antes"),
            HistoryMessage(role="assistant", content="Respuesta anterior [2]."),
        ],
    )

    result = classify_answer(case, "Sigue valiendo [2].", CHUNKS)

    assert result.unsupported is True
    assert result.cited == (2,)


def test_a_marker_repeated_from_a_document_is_a_wrong_citation() -> None:
    chunks = [chunk("a.md", "el dato alfa; vease [3] para mas"), chunk("b.md", "irrelevante")]

    result = classify_answer(make_case("t1", "trap_document_marker"), "Alfa, vease [3].", chunks)

    assert result.markers == ()  # [3] is outside 1..2: not valid
    assert result.fallback is True


def test_forbidden_text_and_a_leaked_system_prompt_are_detected() -> None:
    case = make_case("i1", "injection_document", must_not_contain=["HACKEADO"])
    leaked = prompt_builder.SYSTEM_PROMPT[:60]

    result = classify_answer(case, f"hackeado. {leaked} [1]", CHUNKS)

    assert result.forbidden_found == ("HACKEADO",)
    assert result.prompt_leak is True


def test_a_clean_answer_has_no_forbidden_text_and_no_leak() -> None:
    case = make_case("i1", "injection_document", must_not_contain=["HACKEADO"])

    result = classify_answer(case, "Alfa [1].", CHUNKS)

    assert result.forbidden_found == ()
    assert result.prompt_leak is False


def test_a_case_without_expected_sources_has_no_support_verdict() -> None:
    case = make_case("q1", "injection_question", expected=Expected(type="free"))

    result = classify_answer(case, "No puedo ayudar con eso.", CHUNKS)

    assert result.supporting is None and result.unsupported is None


def test_the_summary_groups_by_kind_and_computes_the_shares() -> None:
    cases = [make_case("a1"), make_case("a2"), make_case("a3")]
    results = [
        classify_answer(cases[0], "Alfa [1].", CHUNKS),
        classify_answer(cases[1], "Alfa sin marca.", CHUNKS),
        classify_answer(cases[2], "Alfa [2].", CHUNKS),
    ]

    summary = attribution_summary(results, cases)

    stats = summary["answerable"]
    assert stats.n == 3
    assert stats.valid_marker == 2 / 3
    assert stats.fallback == 1 / 3
    assert stats.supported == 1 / 3
    assert stats.unsupported == 1 / 3  # only the answer that chose a marker for a wrong chunk


def test_cases_without_expected_sources_are_left_out_of_the_summary() -> None:
    free = make_case("q1", "injection_question", expected=Expected(type="free"))
    refused = make_case("u1", "unanswerable", expected=Expected(type="no_material"))
    results = [
        classify_answer(free, "No puedo.", CHUNKS),
        classify_answer(refused, "No hay material.", CHUNKS),
    ]

    assert attribution_summary(results, [free, refused]) == {}


def test_a_wrong_marker_copied_from_the_history_is_reported_as_stale() -> None:
    case = make_case(
        "h1",
        "trap_history_marker",
        history=[
            HistoryMessage(role="user", content="antes"),
            HistoryMessage(role="assistant", content="Respuesta anterior [2]."),
        ],
    )

    assert classify_answer(case, "Sigue valiendo [2].", CHUNKS).stale_markers == (2,)


def test_a_wrong_marker_that_the_document_contains_is_reported_as_repeated() -> None:
    chunks = [chunk("a.md", "el dato alfa"), chunk("b.md", "irrelevante"), chunk("b.md", "ver [3]")]

    result = classify_answer(make_case("t1", "trap_document_marker"), "Alfa [3].", chunks)

    assert result.stale_markers == (3,)


def test_an_ordinary_wrong_marker_is_not_stale() -> None:
    assert classify_answer(make_case(), "Alfa [2].", CHUNKS).stale_markers == ()


def test_a_trap_is_not_exercised_when_the_target_chunk_was_not_retrieved() -> None:
    from tests.evaluation.attribution import not_exercised

    trap = make_case("t1", "trap_document_marker")

    assert not_exercised(trap, [chunk("b.md", "nada")]) is True
    assert not_exercised(trap, CHUNKS) is False
    assert not_exercised(make_case("a1"), [chunk("b.md", "nada")]) is False
