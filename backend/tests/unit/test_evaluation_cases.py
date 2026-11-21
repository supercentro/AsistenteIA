"""Golden set loader of the evaluation harness (change rag-golden-set-evaluation, task 1.1)."""

import json
from pathlib import Path

import pytest

from tests.evaluation.cases import GoldenSetError, load_golden_set

PASSAGE = "La fotosintesis ocurre en los cloroplastos de las celulas vegetales."


def make_set(tmp_path: Path, cases: list[dict[str, object]], version: str = "t-1") -> Path:
    (tmp_path / "corpus" / "bio").mkdir(parents=True)
    (tmp_path / "corpus" / "bio" / "plantas.md").write_text(PASSAGE + "\n", encoding="utf-8")
    (tmp_path / "corpus" / "fis").mkdir(parents=True)
    (tmp_path / "corpus" / "fis" / "luz.txt").write_text("La luz viaja rapido.\n", "utf-8")
    (tmp_path / "VERSION").write_text(version + "\n", encoding="utf-8")
    (tmp_path / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    return tmp_path


def answerable(case_id: str = "a1", **changes: object) -> dict[str, object]:
    case: dict[str, object] = {
        "id": case_id,
        "kind": "answerable",
        "subject": "bio",
        "question": "Donde ocurre la fotosintesis?",
        "expected": {
            "type": "sources",
            "sources": [{"filename": "plantas.md", "passage_contains": "fotosintesis ocurre"}],
        },
    }
    case.update(changes)
    return case


def test_a_complete_set_loads_with_version_documents_and_cases(tmp_path: Path) -> None:
    root = make_set(tmp_path, [answerable()])

    golden = load_golden_set(root)

    assert golden.version == "t-1"
    assert [case.id for case in golden.cases] == ["a1"]
    assert {doc.filename for doc in golden.documents} == {"plantas.md", "luz.txt"}
    assert golden.subject_of_filename("plantas.md") == "bio"
    plantas = next(doc for doc in golden.documents if doc.filename == "plantas.md")
    assert plantas.content_type == "text/markdown"
    assert PASSAGE.encode() in plantas.payload


def test_a_case_without_a_question_fails_naming_the_case(tmp_path: Path) -> None:
    broken = answerable("sin-pregunta")
    del broken["question"]

    with pytest.raises(GoldenSetError, match="sin-pregunta"):
        load_golden_set(make_set(tmp_path, [broken]))


def test_a_case_without_an_expected_outcome_fails_naming_the_case(tmp_path: Path) -> None:
    broken = answerable("sin-esperado")
    del broken["expected"]

    with pytest.raises(GoldenSetError, match="sin-esperado"):
        load_golden_set(make_set(tmp_path, [broken]))


def test_an_unknown_kind_fails_naming_the_case(tmp_path: Path) -> None:
    with pytest.raises(GoldenSetError, match="raro"):
        load_golden_set(make_set(tmp_path, [answerable("raro", kind="inventado")]))


def test_duplicate_ids_fail(tmp_path: Path) -> None:
    with pytest.raises(GoldenSetError, match="a1"):
        load_golden_set(make_set(tmp_path, [answerable("a1"), answerable("a1")]))


def test_an_accepted_passage_missing_from_the_corpus_fails(tmp_path: Path) -> None:
    case = answerable(
        "fantasma",
        expected={
            "type": "sources",
            "sources": [{"filename": "plantas.md", "passage_contains": "texto que no existe"}],
        },
    )

    with pytest.raises(GoldenSetError, match="fantasma"):
        load_golden_set(make_set(tmp_path, [case]))


def test_an_unknown_subject_fails(tmp_path: Path) -> None:
    with pytest.raises(GoldenSetError, match="x1"):
        load_golden_set(make_set(tmp_path, [answerable("x1", subject="quimica")]))


def test_kind_and_expected_outcome_must_agree(tmp_path: Path) -> None:
    case = answerable("mal", kind="unanswerable")  # unanswerable needs expected no_material

    with pytest.raises(GoldenSetError, match="mal"):
        load_golden_set(make_set(tmp_path, [case]))


def test_a_follow_up_needs_earlier_messages(tmp_path: Path) -> None:
    case = answerable("seg", kind="follow_up")

    with pytest.raises(GoldenSetError, match="seg"):
        load_golden_set(make_set(tmp_path, [case]))


def test_the_same_filename_in_two_subjects_is_refused(tmp_path: Path) -> None:
    root = make_set(tmp_path, [answerable()])
    (root / "corpus" / "fis" / "plantas.md").write_text("otro\n", encoding="utf-8")

    with pytest.raises(GoldenSetError, match="plantas.md"):
        load_golden_set(root)


def test_the_number_of_model_cases_is_counted(tmp_path: Path) -> None:
    cases = [answerable("a1", model=True), answerable("a2"), answerable("a3", model=True)]

    golden = load_golden_set(make_set(tmp_path, cases))

    assert golden.model_case_count == 2


def test_the_shipped_golden_set_is_valid_and_fits_the_call_cap() -> None:
    root = Path(__file__).resolve().parents[1] / "evaluation" / "golden_set"

    golden = load_golden_set(root)

    assert len(golden.cases) >= 70
    assert golden.model_case_count <= 50
    assert {case.kind for case in golden.cases} >= {
        "answerable",
        "unanswerable",
        "follow_up",
        "trap_history_marker",
        "trap_document_marker",
        "injection_question",
        "injection_document",
        "cross_subject",
        "not_enrolled",
    }
    assert "fictitious" in (root / "README.md").read_text(encoding="utf-8").lower()


def test_a_subset_of_cases_can_be_selected_by_id(tmp_path: Path) -> None:
    from tests.evaluation.cases import select_cases

    golden = load_golden_set(make_set(tmp_path, [answerable("a1"), answerable("a2")]))

    subset = select_cases(golden, ["a2"])

    assert [case.id for case in subset.cases] == ["a2"]
    assert subset.documents == golden.documents


def test_selecting_an_unknown_case_fails_naming_it(tmp_path: Path) -> None:
    from tests.evaluation.cases import select_cases

    golden = load_golden_set(make_set(tmp_path, [answerable("a1")]))

    with pytest.raises(GoldenSetError, match="zzz"):
        select_cases(golden, ["zzz"])
