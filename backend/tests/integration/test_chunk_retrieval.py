"""`ChunkRepository.find_similar`: authorization inside the SQL, ranking, limits, recall, leaks."""

import logging
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.database import create_db_engine, create_session_factory
from app.core.vector_validation import InvalidSearchInputError
from app.models.user import UserRole
from app.repositories.chunk_repository import ChunkRepository, ScoredChunk, SearchActor
from tests import embeddings as emb
from tests.catalog import Catalog, build_catalog
from tests.leak_support import build_violations, spy_on_logs
from tests.retrieval_support import build_mixed_dataset
from tests.sql_support import run

TOLERANCE = 1e-6


@pytest.fixture
def catalog(clean_db: str) -> Catalog:
    return build_catalog(clean_db)


def student(user_id: uuid.UUID) -> SearchActor:
    return SearchActor(user_id, UserRole.STUDENT)


def teacher(user_id: uuid.UUID) -> SearchActor:
    return SearchActor(user_id, UserRole.TEACHER)


def search(
    session: Session,
    actor: SearchActor,
    subject: uuid.UUID,
    query: list[float],
    top_k: int = 10,
) -> list[ScoredChunk]:
    return ChunkRepository(session).find_similar(actor, subject, query, top_k)


# ---------------------------------------------------------------- authorization


def test_enrolled_student_gets_only_chunks_of_the_subject(
    db_session: Session, catalog: Catalog
) -> None:
    found = search(db_session, student(catalog.student_algebra), catalog.algebra, catalog.query)
    assert found
    assert {hit.document_filename for hit in found} == {"algebra-ready.pdf"}


def test_owning_teacher_gets_only_chunks_of_the_subject(
    db_session: Session, catalog: Catalog
) -> None:
    found = search(db_session, teacher(catalog.teacher_one), catalog.algebra, catalog.query)
    assert [hit.document_filename for hit in found] == ["algebra-ready.pdf"] * 6


def test_student_enrolled_in_two_subjects_gets_each_subject_separately(
    db_session: Session, catalog: Catalog
) -> None:
    in_physics = search(db_session, student(catalog.student_both), catalog.physics, catalog.query)
    in_algebra = search(db_session, student(catalog.student_both), catalog.algebra, catalog.query)
    assert {hit.document_filename for hit in in_physics} == {"physics.pdf"}
    assert {hit.document_filename for hit in in_algebra} == {"algebra-ready.pdf"}


@pytest.mark.parametrize(
    ("who", "subject"),
    [
        ("student_unenrolled", "algebra"),  # no enrollment at all
        ("student_algebra", "physics"),  # enrolled elsewhere only
        ("student_algebra", "chemistry"),
        ("student_both", "chemistry"),
        ("teacher_two", "algebra"),  # a teacher who does not own the subject
        ("teacher_one", "chemistry"),
    ],
)
def test_unauthorized_actors_get_an_empty_result_without_error(
    db_session: Session, catalog: Catalog, who: str, subject: str
) -> None:
    user_id: uuid.UUID = getattr(catalog, who)
    role = UserRole.TEACHER if who.startswith("teacher") else UserRole.STUDENT
    found = search(db_session, SearchActor(user_id, role), getattr(catalog, subject), catalog.query)
    assert found == []


def test_a_student_id_presented_as_teacher_or_vice_versa_gets_nothing(
    db_session: Session, catalog: Catalog
) -> None:
    """The role is part of the check: ownership is tested for teachers, enrollment for students."""
    as_teacher = SearchActor(catalog.student_algebra, UserRole.TEACHER)
    as_student = SearchActor(catalog.teacher_one, UserRole.STUDENT)
    assert search(db_session, as_teacher, catalog.algebra, catalog.query) == []
    assert search(db_session, as_student, catalog.algebra, catalog.query) == []


def test_unknown_role_gets_an_empty_result(db_session: Session, catalog: Catalog) -> None:
    actor = SearchActor(catalog.teacher_one, "admin")  # type: ignore[arg-type]
    assert search(db_session, actor, catalog.algebra, catalog.query) == []


def test_unknown_subject_gets_an_empty_result(db_session: Session, catalog: Catalog) -> None:
    assert search(db_session, student(catalog.student_both), uuid.uuid4(), catalog.query) == []
    assert search(db_session, teacher(catalog.teacher_one), uuid.uuid4(), catalog.query) == []


def test_unknown_actor_gets_an_empty_result(db_session: Session, catalog: Catalog) -> None:
    assert search(db_session, student(uuid.uuid4()), catalog.algebra, catalog.query) == []


def test_removed_enrollment_takes_effect_on_the_next_call(
    clean_db: str, db_session: Session, catalog: Catalog
) -> None:
    actor = student(catalog.student_algebra)
    assert search(db_session, actor, catalog.algebra, catalog.query)
    run(
        clean_db,
        "DELETE FROM enrollments WHERE subject_id = :s AND student_id = :u",
        s=catalog.algebra,
        u=catalog.student_algebra,
    )
    assert search(db_session, actor, catalog.algebra, catalog.query) == []


def test_other_subjects_are_never_returned_even_when_nearer(
    db_session: Session, catalog: Catalog
) -> None:
    """Physics and Chemistry hold chunks exactly on the query; Algebra's best is 10 degrees away."""
    found = search(db_session, teacher(catalog.teacher_one), catalog.algebra, catalog.query)
    assert len(found) == 6
    assert all(hit.similarity < 0.99 for hit in found)
    assert {hit.document_filename for hit in found} == {"algebra-ready.pdf"}


def test_a_subject_with_fewer_chunks_than_top_k_returns_only_its_own(
    db_session: Session, catalog: Catalog
) -> None:
    found = search(db_session, teacher(catalog.teacher_two), catalog.chemistry, catalog.query, 50)
    assert [hit.document_filename for hit in found] == ["chemistry.pdf"]


# ---------------------------------------------------------------- ranking and content


def test_ranking_matches_the_known_similarities(db_session: Session, catalog: Catalog) -> None:
    found = search(db_session, student(catalog.student_algebra), catalog.algebra, catalog.query)
    assert [(hit.document_filename, hit.chunk_index) for hit in found] == [
        (expected.filename, expected.chunk_index) for expected in catalog.algebra_ready_ranking
    ]
    for hit, expected in zip(found, catalog.algebra_ready_ranking, strict=True):
        assert hit.similarity == pytest.approx(expected.similarity, abs=TOLERANCE)


def test_results_carry_every_documented_field(db_session: Session, catalog: Catalog) -> None:
    best = search(db_session, student(catalog.student_algebra), catalog.algebra, catalog.query, 1)[
        0
    ]
    assert best.document_id == catalog.documents["algebra-ready.pdf"]
    assert isinstance(best.chunk_id, uuid.UUID)
    assert best.document_filename == "algebra-ready.pdf"
    assert best.chunk_index == 0
    assert best.page_number == 1
    assert best.content == "fixture chunk algebra-ready.pdf 0"
    assert isinstance(best.similarity, float)


def test_scored_chunk_is_immutable() -> None:
    chunk = ScoredChunk(uuid.uuid4(), uuid.uuid4(), "f.pdf", 0, None, "text", 0.5)
    with pytest.raises(AttributeError):
        chunk.similarity = 1.0  # type: ignore[misc]


def test_search_actor_is_immutable() -> None:
    actor = SearchActor(uuid.uuid4(), UserRole.STUDENT)
    with pytest.raises(AttributeError):
        actor.role = UserRole.TEACHER  # type: ignore[misc]


def test_limit_returns_exactly_top_k_in_order(db_session: Session, catalog: Catalog) -> None:
    found = search(db_session, student(catalog.student_algebra), catalog.algebra, catalog.query, 3)
    assert [hit.chunk_index for hit in found] == [0, 1, 2]


def test_only_ready_documents_are_returned(db_session: Session, catalog: Catalog) -> None:
    """Pending, processing and failed Algebra documents hold chunks exactly on the query."""
    found = search(db_session, teacher(catalog.teacher_one), catalog.algebra, catalog.query, 50)
    names = {hit.document_filename for hit in found}
    assert names == {"algebra-ready.pdf"}
    assert not any(name in names for name in ("algebra-pending.pdf", "algebra-failed.pdf"))


def test_ties_are_broken_by_chunk_id(clean_db: str, db_session: Session) -> None:
    from tests.sql_support import insert_chunk, seed_basic

    seed = seed_basic(clean_db)
    vector = emb.to_literal(emb.basis(0))
    for index in range(12):
        insert_chunk(clean_db, seed.document_id, seed.subject_id, index, vector)
    found = search(db_session, student(seed.student_id), seed.subject_id, emb.basis(0), 12)
    ids = [hit.chunk_id for hit in found]
    assert len(set(ids)) == 12
    assert ids == sorted(ids)  # equal similarity: the documented tie-break is the chunk id


# ---------------------------------------------------------------- recall against an exact search


def test_results_are_complete_with_many_subjects_and_equal_the_exact_search(
    clean_db: str, db_session: Session
) -> None:
    data = build_mixed_dataset(clean_db)
    assert data.chunk_total >= 1000
    exact = sorted(
        data.target_vectors.items(),
        key=lambda item: emb.cosine_similarity(data.query, item[1]),
        reverse=True,
    )
    for top_k in (1, 5, 20, 50):
        found = search(db_session, student(data.student_id), data.target_subject, data.query, top_k)
        assert len(found) == top_k
        assert [hit.chunk_index for hit in found] == [index for index, _ in exact[:top_k]]
        for hit, (_, vector) in zip(found, exact[:top_k], strict=True):
            assert hit.similarity == pytest.approx(
                emb.cosine_similarity(data.query, vector), abs=TOLERANCE
            )


# ---------------------------------------------------------------- numeric accuracy


def _single(vector: list[float]) -> list[float]:
    import struct

    return [struct.unpack("f", struct.pack("f", x))[0] for x in vector]


@pytest.mark.parametrize("norm", [1e-6, 1e6])
def test_similarities_at_the_edges_of_the_norm_range_are_accurate(
    db_session: Session, catalog: Catalog, norm: float
) -> None:
    query = emb.scaled(catalog.query, norm)
    found = search(db_session, teacher(catalog.teacher_one), catalog.algebra, query)
    assert len(found) == 6
    for hit, expected in zip(found, catalog.algebra_ready_ranking, strict=True):
        assert hit.similarity == pytest.approx(expected.similarity, abs=TOLERANCE)


def test_extremely_uneven_components_match_an_exact_computation(
    clean_db: str, db_session: Session
) -> None:
    from tests.sql_support import insert_chunk, seed_basic

    seed = seed_basic(clean_db)
    uneven_query = [1e-3] * 384
    uneven_query[0] = 5e5  # norm about 5e5: in range, dominated by one component
    stored = [
        [1e-3] * 384,
        [2e-3 if i % 2 else 1e-3 for i in range(384)],
        [1.0] + [1e-4] * 383,
    ]
    stored[0][0] = 4e5
    for index, vector in enumerate(stored):
        insert_chunk(clean_db, seed.document_id, seed.subject_id, index, emb.to_literal(vector))
    found = search(db_session, student(seed.student_id), seed.subject_id, uneven_query, 3)
    reference = {
        index: emb.cosine_similarity(_single(uneven_query), _single(vector))
        for index, vector in enumerate(stored)
    }
    assert len(found) == 3
    for hit in found:
        assert hit.similarity == pytest.approx(reference[hit.chunk_index], abs=TOLERANCE)
    assert [hit.chunk_index for hit in found] == sorted(
        reference, key=reference.__getitem__, reverse=True
    )


# ---------------------------------------------------------------- invalid input stays out of the DB


def _statement_counter(engine: Engine) -> list[str]:
    seen: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _record(*args: Any) -> None:  # (conn, cursor, statement, ...)
        seen.append(str(args[2]))

    return seen


@pytest.fixture
def counting_session(clean_db: str) -> Iterator[tuple[Session, list[str]]]:
    engine = create_db_engine(clean_db)
    statements = _statement_counter(engine)
    session = create_session_factory(engine)()
    try:
        yield session, statements
    finally:
        session.close()
        engine.dispose()


def _bad_inputs(query: list[float]) -> list[tuple[list[float], int]]:
    nan = list(query)
    nan[3] = float("nan")
    inf = list(query)
    inf[3] = float("inf")
    return [
        (query[:383], 5),
        (query + [0.0], 5),
        ([], 5),
        ([0.0] * 384, 5),
        (nan, 5),
        (inf, 5),
        (emb.scaled(query, 1e-7), 5),
        (emb.scaled(query, 1e7), 5),
        (query, 0),
        (query, -1),
        (query, 51),
    ]


def test_invalid_input_is_rejected_without_executing_any_statement(
    counting_session: tuple[Session, list[str]], catalog: Catalog
) -> None:
    session, statements = counting_session
    for bad_query, top_k in _bad_inputs(catalog.query):
        with pytest.raises(InvalidSearchInputError):
            ChunkRepository(session).find_similar(
                teacher(catalog.teacher_one), catalog.algebra, bad_query, top_k
            )
    assert statements == []


def test_invalid_input_never_touches_the_session() -> None:
    session = MagicMock(spec=Session)
    with pytest.raises(InvalidSearchInputError):
        ChunkRepository(session).find_similar(teacher(uuid.uuid4()), uuid.uuid4(), [0.0] * 384, 5)
    session.execute.assert_not_called()


def test_a_valid_search_executes_exactly_one_statement(
    counting_session: tuple[Session, list[str]], catalog: Catalog
) -> None:
    session, statements = counting_session
    found = ChunkRepository(session).find_similar(
        teacher(catalog.teacher_one), catalog.algebra, catalog.query, 5
    )
    assert len(found) == 5
    assert len(statements) == 1


def test_the_statement_itself_checks_authorization_subject_and_status(
    counting_session: tuple[Session, list[str]], catalog: Catalog
) -> None:
    session, statements = counting_session
    repository = ChunkRepository(session)
    repository.find_similar(student(catalog.student_algebra), catalog.algebra, catalog.query, 5)
    repository.find_similar(teacher(catalog.teacher_one), catalog.algebra, catalog.query, 5)
    student_sql, teacher_sql = (statement.lower() for statement in statements)
    for sql in (student_sql, teacher_sql):
        assert "document_chunks.subject_id" in sql
        assert "documents.status" in sql
        assert "exists" in sql
    assert "enrollments.student_id" in student_sql
    assert "subjects.teacher_id" in teacher_sql


# ---------------------------------------------------------------- concurrency


def test_parallel_searches_by_different_actors_stay_isolated(
    clean_db: str, catalog: Catalog
) -> None:
    jobs = [
        (student(catalog.student_both), catalog.algebra, "algebra-ready.pdf"),
        (student(catalog.student_both), catalog.physics, "physics.pdf"),
        (teacher(catalog.teacher_one), catalog.algebra, "algebra-ready.pdf"),
        (teacher(catalog.teacher_one), catalog.physics, "physics.pdf"),
        (teacher(catalog.teacher_two), catalog.chemistry, "chemistry.pdf"),
        (student(catalog.student_algebra), catalog.algebra, "algebra-ready.pdf"),
        (student(catalog.student_unenrolled), catalog.algebra, None),
        (teacher(catalog.teacher_two), catalog.algebra, None),
        (student(catalog.student_algebra), catalog.chemistry, None),
    ] * 8

    def work(job: tuple[SearchActor, uuid.UUID, str | None]) -> tuple[set[str], str | None]:
        actor, subject, expected = job
        engine = create_db_engine(clean_db)
        try:
            with create_session_factory(engine)() as session:
                found = ChunkRepository(session).find_similar(actor, subject, catalog.query, 10)
        finally:
            engine.dispose()
        return {hit.document_filename for hit in found}, expected

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(work, jobs))
    for names, expected in outcomes:
        assert names == (set() if expected is None else {expected})


# ---------------------------------------------------------------- logs and error text (I2)


FORBIDDEN_TEXT = (
    "fixture chunk",
    "[1.0,0.0,0.0",  # how pgvector serialises the query embedding
    "[1,0,0,0",
    "0.9848",
    "Failing row contains",
)


def _assert_clean(log_text: str) -> None:
    for fragment in FORBIDDEN_TEXT:
        assert fragment not in log_text


def test_valid_and_rejected_searches_log_no_vector_or_chunk_text(
    clean_db: str, catalog: Catalog
) -> None:
    engine = create_db_engine(clean_db)
    sql_logger = logging.getLogger("sqlalchemy.engine")
    previous = sql_logger.level
    sql_logger.setLevel(
        logging.INFO
    )  # demanding: statement logging on, parameters must stay hidden
    try:
        with spy_on_logs() as spy, create_session_factory(engine)() as session:
            repo = ChunkRepository(session)
            repo.find_similar(teacher(catalog.teacher_one), catalog.algebra, catalog.query, 5)
            for bad_query, top_k in _bad_inputs(catalog.query):
                with pytest.raises(InvalidSearchInputError):
                    repo.find_similar(
                        teacher(catalog.teacher_one), catalog.algebra, bad_query, top_k
                    )
    finally:
        sql_logger.setLevel(previous)
        engine.dispose()
    assert spy.text  # the statement itself was logged, so the check is meaningful
    assert "hidden" in spy.text  # SQLAlchemy states that the parameters are hidden
    _assert_clean(spy.text)


def test_a_database_failure_in_the_search_path_surfaces_without_row_data(
    clean_db: str, catalog: Catalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real SQL exception carrying row data is raised where the search statement runs."""
    from fastapi.testclient import TestClient

    from tests.integration.helpers import build_app
    from tests.leak_support import CONTENT_MARKER, EMBEDDING_MARKER, ROW_DETAIL_MARKER

    violation = next(v for v in build_violations(clean_db) if v.name == "check_violation")
    app = build_app(clean_db)
    engine = create_db_engine(clean_db)

    def probe() -> dict[str, str]:
        with create_session_factory(engine)() as session:

            def failing_execute(*args: object, **kwargs: object) -> None:
                violation.execute()  # raises the real DBAPIError with the failing row in DETAIL

            monkeypatch.setattr(session, "execute", failing_execute)
            ChunkRepository(session).find_similar(
                teacher(catalog.teacher_one), catalog.algebra, catalog.query, 5
            )
        return {"status": "no error"}

    app.add_api_route("/_probe", probe, methods=["GET"])
    try:
        with spy_on_logs() as spy, TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/_probe")
    finally:
        engine.dispose()
    assert response.status_code == 500
    assert response.json() == {"code": "INTERNAL_ERROR", "message": "Internal server error"}
    for marker in (CONTENT_MARKER, EMBEDDING_MARKER, ROW_DETAIL_MARKER, "fixture chunk"):
        assert marker not in response.text
        assert marker not in spy.text


def test_the_repository_does_not_swallow_or_rewrite_database_errors(
    clean_db: str, catalog: Catalog, monkeypatch: pytest.MonkeyPatch
) -> None:
    violation = next(v for v in build_violations(clean_db) if v.name == "check_violation")
    engine = create_db_engine(clean_db)
    try:
        with create_session_factory(engine)() as session:
            monkeypatch.setattr(session, "execute", lambda *a, **k: violation.execute())
            with pytest.raises(Exception) as raised:  # noqa: PT011
                ChunkRepository(session).find_similar(
                    teacher(catalog.teacher_one), catalog.algebra, catalog.query, 5
                )
    finally:
        engine.dispose()
    assert not isinstance(raised.value, InvalidSearchInputError)


def test_there_is_no_unscoped_read_method() -> None:
    public = {name for name in dir(ChunkRepository) if not name.startswith("_")}
    assert public == {"find_similar"}
