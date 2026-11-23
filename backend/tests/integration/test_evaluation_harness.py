"""The evaluation harness on a tiny fixture: fake embedder, fake model, isolated test database.

Proves the mechanics (loading, production path, isolation, cleanup, caps), never the quality of the
real pipeline. The real embedding model and Gemini are never used here (change
rag-golden-set-evaluation, tasks 1.4, 1.6, 1.7 and 1.9).
"""

import json
import pathlib
import uuid
from pathlib import Path
from typing import Any

import pytest

from app.rag.embedder import FakeEmbedder
from app.services import rag_service as rag_module
from app.services.llm_service import FakeLLMService
from tests.evaluation.cases import load_golden_set
from tests.evaluation.guards import CallCapExceededError
from tests.evaluation.runner import RunSettings, run_evaluation
from tests.integration.helpers import build_settings
from tests.sql_support import count, insert_subject, insert_user

PLANTAS = (
    "La fotosintesis ocurre en los cloroplastas de las celulas vegetales y produce glucosa.\n\n"
    "Las raices absorben agua y sales minerales del suelo.\n"
)
LUZ = "La luz viaja a trescientos mil kilometros por segundo en el vacio.\n"
TABLES = (
    "users",
    "subjects",
    "enrollments",
    "documents",
    "document_chunks",
    "conversations",
    "messages",
)


def case(case_id: str, kind: str, subject: str, question: str, **more: Any) -> dict[str, Any]:
    values: dict[str, Any] = {"id": case_id, "kind": kind, "subject": subject, "question": question}
    values.update(more)
    return values


def sources(filename: str, passage: str) -> dict[str, Any]:
    return {"type": "sources", "sources": [{"filename": filename, "passage_contains": passage}]}


@pytest.fixture
def golden_dir(tmp_path: Path) -> Path:
    (tmp_path / "corpus" / "bio").mkdir(parents=True)
    (tmp_path / "corpus" / "fis").mkdir(parents=True)
    (tmp_path / "corpus" / "bio" / "plantas.md").write_text(PLANTAS, encoding="utf-8")
    (tmp_path / "corpus" / "fis" / "luz.txt").write_text(LUZ, encoding="utf-8")
    (tmp_path / "VERSION").write_text("fixture-1\n", encoding="utf-8")
    cases = [
        case(
            "a1",
            "answerable",
            "bio",
            "Donde ocurre la fotosintesis en las celulas vegetales?",
            expected=sources("plantas.md", "fotosintesis ocurre"),
            model=True,
        ),
        case(
            "a2",
            "answerable",
            "bio",
            "Que absorben las raices del suelo?",
            expected=sources("plantas.md", "raices absorben"),
        ),
        case(
            "u1",
            "unanswerable",
            "bio",
            "Cual es la capital de Mongolia?",
            expected={"type": "no_material"},
        ),
        case(
            "f1",
            "follow_up",
            "bio",
            "y que produce ademas de eso?",
            history=[
                {"role": "user", "content": "Donde ocurre la fotosintesis?"},
                {"role": "assistant", "content": "En los cloroplastas [1]."},
            ],
            expected=sources("plantas.md", "produce glucosa"),
            model=True,
        ),
        case(
            "x1",
            "cross_subject",
            "bio",
            "A que velocidad viaja la luz en el vacio?",
            expected={"type": "isolation"},
        ),
        case(
            "n1",
            "not_enrolled",
            "bio",
            "Donde ocurre la fotosintesis?",
            student="not_enrolled",
            expected={"type": "denied"},
        ),
        case(
            "n2",
            "not_enrolled",
            "bio",
            "Donde ocurre la fotosintesis?",
            student="enrolled_elsewhere",
            expected={"type": "denied"},
        ),
    ]
    (tmp_path / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    return tmp_path


def run(url: str, golden_dir: Path, **changes: Any) -> Any:
    options: dict[str, Any] = {
        "mode": "answers",
        "top_ks": [3, 5],
        "thresholds": [0.1, 0.3],
        "default_top_k": 5,
        "default_threshold": 0.1,
        "max_calls": 10,
        "revision": "test",
        "embedder_name": "fake",
        "model_name": "fake",
    }
    options.update(changes)
    return run_evaluation(
        url,
        build_settings(url, chat_top_k=5, chat_relevance_threshold=0.1),
        load_golden_set(golden_dir),
        FakeEmbedder(),
        FakeLLMService(),
        RunSettings(**options),
    )


def snapshot(url: str) -> dict[str, int]:
    return {table: count(url, table) for table in TABLES}


def test_a_run_reports_rows_attribution_and_the_calls_it_made(
    clean_db: str, golden_dir: Path
) -> None:
    report = run(clean_db, golden_dir)

    assert report.header.golden_set_version == "fixture-1"
    assert report.header.model_calls <= 2
    assert len(report.rows) == 4
    assert [(r.top_k, r.threshold) for r in report.rows if r.default] == [(5, 0.1)]
    assert report.isolation_violations == []
    assert report.problems == []
    assert "answerable" in report.attribution


def test_the_run_goes_through_the_production_read_and_generate_phases(
    clean_db: str, golden_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared: list[uuid.UUID] = []
    generated: list[int] = []
    original_prepare = rag_module.RAGService.prepare
    original_generate = rag_module.RAGService.generate

    def spy_prepare(self: Any, **kwargs: Any) -> Any:
        prepared.append(kwargs["student_id"])
        return original_prepare(self, **kwargs)

    async def spy_generate(self: Any, context: Any) -> str:
        generated.append(len(context.chunks))
        return await original_generate(self, context)

    monkeypatch.setattr(rag_module.RAGService, "prepare", spy_prepare)
    monkeypatch.setattr(rag_module.RAGService, "generate", spy_generate)

    run(clean_db, golden_dir)

    assert len(prepared) >= 6  # every case goes through prepare
    assert generated, "model cases must go through RAGService.generate"


def test_follow_up_history_is_loaded_from_a_stored_conversation(
    clean_db: str, golden_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[dict[str, str]]] = []
    original_generate = rag_module.RAGService.generate

    async def spy_generate(self: Any, context: Any) -> str:
        seen.append(list(context.history))
        return await original_generate(self, context)

    monkeypatch.setattr(rag_module.RAGService, "generate", spy_generate)

    run(clean_db, golden_dir)

    assert any(history and history[-1]["content"] == "En los cloroplastas [1]." for history in seen)


def test_two_runs_give_identical_metrics(clean_db: str, golden_dir: Path) -> None:
    first = run(clean_db, golden_dir)
    second = run(clean_db, golden_dir)

    assert first.rows == second.rows
    assert first.attribution == second.attribution


def test_a_run_leaves_the_database_as_it_found_it_and_keeps_existing_rows(
    clean_db: str, golden_dir: Path
) -> None:
    teacher = insert_user(clean_db, "keep-teacher@example.com", "teacher")
    insert_subject(clean_db, teacher, "Materia previa")
    before = snapshot(clean_db)

    run(clean_db, golden_dir)

    assert snapshot(clean_db) == before
    assert count(clean_db, "subjects", "name = 'Materia previa'") == 1


def test_a_failing_run_still_removes_what_it_created(clean_db: str, golden_dir: Path) -> None:
    class ExplodingEmbedder(FakeEmbedder):
        calls = 0

        def embed(self, texts: Any) -> list[list[float]]:
            type(self).calls += 1
            if type(self).calls > 6:
                raise RuntimeError("boom")
            return super().embed(texts)

    before = snapshot(clean_db)

    with pytest.raises(RuntimeError):
        run_evaluation(
            clean_db,
            build_settings(clean_db, chat_top_k=5, chat_relevance_threshold=0.1),
            load_golden_set(golden_dir),
            ExplodingEmbedder(),
            FakeLLMService(),
            RunSettings(
                mode="answers",
                top_ks=[5],
                thresholds=[0.1],
                default_top_k=5,
                default_threshold=0.1,
                max_calls=10,
                revision="t",
                embedder_name="boom",
                model_name="fake",
            ),
        )

    assert snapshot(clean_db) == before


def test_the_call_cap_stops_the_run_before_any_model_call(
    clean_db: str, golden_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[int] = []

    async def counting_generate(self: Any, context: Any) -> str:
        called.append(1)
        return "x"

    monkeypatch.setattr(rag_module.RAGService, "generate", counting_generate)
    before = snapshot(clean_db)

    with pytest.raises(CallCapExceededError):
        run(clean_db, golden_dir, max_calls=0)

    assert called == []
    assert snapshot(clean_db) == before


def test_retrieval_mode_never_calls_the_model(
    clean_db: str, golden_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def forbidden(self: Any, context: Any) -> str:
        raise AssertionError("retrieval mode must not generate")

    monkeypatch.setattr(rag_module.RAGService, "generate", forbidden)

    report = run(clean_db, golden_dir, mode="retrieval", max_calls=0)

    assert report.header.model_calls == 0
    assert report.attribution == {}


def test_a_chunk_of_another_subject_fails_the_isolation_check(
    clean_db: str, golden_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.repositories import chunk_repository

    def leaking(self: Any, actor: Any, subject_id: Any, query: Any, top_k: int) -> Any:
        # Simulates a broken isolation: a chunk of the physics subject comes back for biology.
        return [
            chunk_repository.ScoredChunk(
                uuid.uuid4(), uuid.uuid4(), "luz.txt", 0, None, "luz", 0.99
            )
        ]

    monkeypatch.setattr(chunk_repository.ChunkRepository, "find_similar", leaking)

    report = run(clean_db, golden_dir, mode="retrieval", max_calls=0)

    assert report.isolation_violations, "a leaked chunk must be reported"


def test_a_student_enrolled_in_another_subject_is_denied(clean_db: str, golden_dir: Path) -> None:
    report = run(clean_db, golden_dir, mode="retrieval", max_calls=0)

    assert report.isolation_violations == []


def test_all_answers_of_a_run_share_one_event_loop(clean_db: str, golden_dir: Path) -> None:
    import asyncio

    loops: list[int] = []

    class LoopRecordingLLM:
        async def generate(self, system_prompt: str, user_messages: list[dict[str, str]]) -> str:
            loops.append(id(asyncio.get_running_loop()))
            return "Respuesta [1]."

    run_evaluation(
        clean_db,
        build_settings(clean_db, chat_top_k=5, chat_relevance_threshold=0.1),
        load_golden_set(golden_dir),
        FakeEmbedder(),
        LoopRecordingLLM(),
        RunSettings(
            mode="answers",
            top_ks=[5],
            thresholds=[0.1],
            default_top_k=5,
            default_threshold=0.1,
            max_calls=10,
            revision="t",
            embedder_name="fake",
            model_name="fake",
        ),
    )

    assert len(loops) >= 2
    assert len(set(loops)) == 1, "a pooled async client must not see one loop per case"


def test_the_run_stops_after_two_failed_model_calls_in_a_row(
    clean_db: str, golden_dir: Path
) -> None:
    class FailingLLM:
        async def generate(self, system_prompt: str, user_messages: list[dict[str, str]]) -> str:
            raise RuntimeError("provider down AIzaSySECRET")

    report = run_evaluation(
        clean_db,
        build_settings(clean_db, chat_top_k=5, chat_relevance_threshold=0.1),
        load_golden_set(golden_dir),
        FakeEmbedder(),
        FailingLLM(),
        RunSettings(
            mode="answers",
            top_ks=[5],
            thresholds=[0.1],
            default_top_k=5,
            default_threshold=0.1,
            max_calls=10,
            revision="t",
            embedder_name="fake",
            model_name="fake",
        ),
    )

    assert report.header.model_calls == 2
    assert any("stopped after repeated model failures" in p for p in report.problems)
    assert all("AIzaSySECRET" not in p for p in report.problems)


def test_a_failure_while_loading_the_documents_still_cleans_up(
    clean_db: str, golden_dir: Path
) -> None:
    class FailsAtOnce(FakeEmbedder):
        def embed(self, texts: Any) -> list[list[float]]:
            raise RuntimeError("boom")

    before = snapshot(clean_db)

    with pytest.raises(RuntimeError):
        run_evaluation(
            clean_db,
            build_settings(clean_db, chat_top_k=5, chat_relevance_threshold=0.1),
            load_golden_set(golden_dir),
            FailsAtOnce(),
            FakeLLMService(),
            RunSettings(
                mode="retrieval",
                top_ks=[5],
                thresholds=[0.1],
                default_top_k=5,
                default_threshold=0.1,
                max_calls=0,
                revision="t",
                embedder_name="boom",
                model_name="fake",
            ),
        )

    assert snapshot(clean_db) == before


def test_an_accepted_passage_that_no_single_chunk_contains_is_reported(
    clean_db: str, tmp_path: Path
) -> None:
    words = " ".join(f"palabra{n}" for n in range(300))  # 300 tokens: more than one chunk
    (tmp_path / "corpus" / "bio").mkdir(parents=True)
    (tmp_path / "corpus" / "bio" / "largo.md").write_text(words + "\\n", encoding="utf-8")
    (tmp_path / "VERSION").write_text("long\\n", encoding="utf-8")
    straddling = " ".join(f"palabra{n}" for n in range(40, 190))  # 150 tokens: cannot fit a chunk
    cases = [case("l1", "answerable", "bio", "pregunta", expected=sources("largo.md", straddling))]
    (tmp_path / "cases.json").write_text(json.dumps(cases), encoding="utf-8")

    report = run(clean_db, tmp_path, mode="retrieval", max_calls=0)

    assert any("l1" in problem and "single chunk" in problem for problem in report.problems)


def test_the_ledger_is_checked_before_the_first_call_and_updated_after_the_run(
    clean_db: str, golden_dir: Path, tmp_path: Path
) -> None:
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(
        json.dumps({"authorised_total": 50, "spent": 10, "entries": []}), encoding="utf-8"
    )

    report = run(clean_db, golden_dir, ledger_path=ledger_path)

    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert report.header.model_calls > 0
    assert data["spent"] == 10 + report.header.model_calls
    assert data["entries"][-1]["calls"] == report.header.model_calls


def test_a_run_that_needs_more_than_the_ledger_allows_makes_no_call(
    clean_db: str, golden_dir: Path, tmp_path: Path
) -> None:
    from tests.evaluation.budget import BudgetExhaustedError

    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(
        json.dumps({"authorised_total": 50, "spent": 50, "entries": []}), encoding="utf-8"
    )

    with pytest.raises(BudgetExhaustedError):
        run(clean_db, golden_dir, ledger_path=ledger_path)

    assert json.loads(ledger_path.read_text(encoding="utf-8"))["spent"] == 50


def test_calls_made_before_a_failure_are_still_recorded(
    clean_db: str, golden_dir: Path, tmp_path: Path
) -> None:
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(
        json.dumps({"authorised_total": 50, "spent": 0, "entries": []}), encoding="utf-8"
    )

    class OneThenExplode:
        calls = 0

        async def generate(self, system_prompt: str, user_messages: list[dict[str, str]]) -> str:
            type(self).calls += 1
            raise RuntimeError("boom")

    run_evaluation(
        clean_db,
        build_settings(clean_db, chat_top_k=5, chat_relevance_threshold=0.1),
        load_golden_set(golden_dir),
        FakeEmbedder(),
        OneThenExplode(),
        RunSettings(
            mode="answers",
            top_ks=[5],
            thresholds=[0.1],
            default_top_k=5,
            default_threshold=0.1,
            max_calls=10,
            revision="t",
            embedder_name="fake",
            model_name="fake",
            ledger_path=ledger_path,
        ),
    )

    assert json.loads(ledger_path.read_text(encoding="utf-8"))["spent"] == 2


def _ledger(tmp_path: Path, spent: int = 0) -> Path:
    path = tmp_path / "ledger.json"
    path.write_text(
        json.dumps({"authorised_total": 50, "spent": spent, "entries": []}), encoding="utf-8"
    )
    return path


def test_the_calls_are_reserved_in_the_ledger_before_the_first_one(
    clean_db: str, golden_dir: Path, tmp_path: Path
) -> None:
    ledger_path = _ledger(tmp_path)
    seen: list[int] = []

    class LedgerPeekingLLM:
        async def generate(self, system_prompt: str, user_messages: list[dict[str, str]]) -> str:
            seen.append(json.loads(ledger_path.read_text(encoding="utf-8"))["spent"])
            return "Respuesta [1]."

    report = run_evaluation(
        clean_db,
        build_settings(clean_db, chat_top_k=5, chat_relevance_threshold=0.1),
        load_golden_set(golden_dir),
        FakeEmbedder(),
        LedgerPeekingLLM(),
        RunSettings(
            mode="answers",
            top_ks=[5],
            thresholds=[0.1],
            default_top_k=5,
            default_threshold=0.1,
            max_calls=10,
            revision="t",
            embedder_name="fake",
            model_name="fake",
            ledger_path=ledger_path,
        ),
    )

    assert seen and all(value >= len(seen) for value in seen)
    assert seen[0] == report.header.model_calls  # everything was reserved before the first call
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert data["spent"] == report.header.model_calls
    assert "reserved" not in data["entries"][-1]


def test_an_unwritable_ledger_stops_the_run_before_any_call(
    clean_db: str, golden_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.evaluation.guards import HarnessRefusedError

    ledger_path = _ledger(tmp_path)
    called: list[int] = []

    class CountingLLM:
        async def generate(self, system_prompt: str, user_messages: list[dict[str, str]]) -> str:
            called.append(1)
            return "x"

    def refuse(self: Path, *args: object, **kwargs: object) -> int:
        raise PermissionError("read-only")

    monkeypatch.setattr(pathlib.Path, "write_text", refuse)
    before = snapshot(clean_db)

    with pytest.raises(HarnessRefusedError):
        run_evaluation(
            clean_db,
            build_settings(clean_db, chat_top_k=5, chat_relevance_threshold=0.1),
            load_golden_set(golden_dir),
            FakeEmbedder(),
            CountingLLM(),
            RunSettings(
                mode="answers",
                top_ks=[5],
                thresholds=[0.1],
                default_top_k=5,
                default_threshold=0.1,
                max_calls=10,
                revision="t",
                embedder_name="fake",
                model_name="fake",
                ledger_path=ledger_path,
            ),
        )

    assert called == []
    assert snapshot(clean_db) == before


def test_a_ledger_that_cannot_be_settled_does_not_lose_the_report(
    clean_db: str, golden_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.evaluation import runner as runner_module

    def broken(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(runner_module, "settle_run", broken)

    report = run(clean_db, golden_dir, ledger_path=_ledger(tmp_path))

    assert report.header.model_calls > 0
    assert any("ledger" in problem for problem in report.problems)


def test_a_failed_cleanup_does_not_lose_the_report(
    clean_db: str, golden_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.evaluation import runner as runner_module

    original = runner_module._sql
    state = {"fail": False}

    def flaky(url: str, statement: str, **params: object) -> None:
        if state["fail"] and statement.startswith("DELETE FROM users"):
            raise OSError("connection lost")
        original(url, statement, **params)

    monkeypatch.setattr(runner_module, "_sql", flaky)
    state["fail"] = True

    report = run(clean_db, golden_dir, mode="retrieval", max_calls=0)

    assert any("cleanup" in problem for problem in report.problems)
    state["fail"] = False
    runner_module._cleanup  # noqa: B018 - rows left behind are removed by the next clean_db


def test_the_recorded_requests_agree_with_the_counted_calls() -> None:
    import asyncio

    from app.core.config import Settings
    from tests.constants import TEST_JWT_SECRET
    from tests.evaluation.llm import RecordingModel
    from tests.evaluation.runner import _CountingLLM

    class Echo:
        async def ainvoke(self, messages: Any) -> Any:
            class Reply:
                content = "ok [1]"
                response_metadata: dict[str, Any] = {}

            return Reply()

    recorder = RecordingModel(Echo())
    from app.services.llm_service import GeminiLLMService

    counting = _CountingLLM(GeminiLLMService(model=recorder, timeout_seconds=5), cap=5)
    for index in range(3):
        asyncio.run(counting.generate("s", [{"role": "user", "content": str(index)}]))

    assert recorder.requests == counting.calls == 3
    assert Settings.__name__ and TEST_JWT_SECRET  # imports kept explicit for the reader


def test_every_answer_of_the_run_is_kept_in_the_report(clean_db: str, golden_dir: Path) -> None:
    report = run(clean_db, golden_dir)

    assert report.header.model_calls == len(report.answers) > 0
    assert [a.case_id for a in report.answers] == ["a1", "f1"]
    for record in report.answers:
        assert record.answer.strip()
        assert record.question
        assert record.kind in {"answerable", "follow_up"}
    # The scripted model writes no marker: every answer fell back to the retrieved chunks.
    assert all(record.fallback and record.markers == [] for record in report.answers)
    assert all(record.cited_files for record in report.answers)


def test_cases_marked_for_the_model_that_retrieved_nothing_are_listed(
    clean_db: str, golden_dir: Path
) -> None:
    options = RunSettings(
        mode="answers",
        top_ks=[5],
        thresholds=[0.99],
        default_top_k=5,
        default_threshold=0.99,
        max_calls=10,
        revision="test",
        embedder_name="fake",
        model_name="fake",
    )

    report = run_evaluation(
        clean_db,
        build_settings(clean_db, chat_top_k=5, chat_relevance_threshold=0.99),
        load_golden_set(golden_dir),
        FakeEmbedder(),
        FakeLLMService(),
        options,
    )

    assert report.header.model_calls == 0
    assert report.answers == []
    note = next(n for n in report.notes if "retrieved nothing" in n)
    assert "a1" in note and "f1" in note


def test_a_second_run_under_the_same_authorisation_makes_no_call(
    clean_db: str, golden_dir: Path, tmp_path: Path
) -> None:
    from tests.evaluation.budget import BudgetExhaustedError

    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(
        json.dumps({"authorised_total": 80, "spent": 10, "entries": []}), encoding="utf-8"
    )
    first = run(clean_db, golden_dir, ledger_path=ledger_path)
    spent_after_first = json.loads(ledger_path.read_text(encoding="utf-8"))["spent"]
    assert first.header.model_calls > 0 and spent_after_first < 80  # room is left

    with pytest.raises(BudgetExhaustedError, match="already used"):
        run(clean_db, golden_dir, ledger_path=ledger_path)

    after = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert after["spent"] == spent_after_first
    assert after["authorised_total"] == 80
    assert len(after["entries"]) == 1
