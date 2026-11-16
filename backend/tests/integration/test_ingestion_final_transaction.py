"""The final transaction of a job: chunks, count, `ready` and erased bytes (change 6, task 7.3)."""

import uuid

import pytest
from sqlalchemy import event, text

from app.core.vector_validation import InvalidSearchInputError, validate_embedding
from app.models.user import UserRole
from app.rag.chunker import Chunk
from app.repositories.chunk_repository import ChunkRepository, SearchActor
from app.repositories.ingestion_job_repository import ClaimedJob, IngestionJobRepository
from tests.ingestion_support import (
    Scene,
    chunk_count,
    document_state,
    expire_lease,
    insert_pending,
    job_state,
    make_scene,
    session_for,
)
from tests.sql_support import run, scalar

LEASE = 120
DIMENSIONS = 384


def vector(index: int, scale: float = 1.0) -> list[float]:
    values = [0.0] * DIMENSIONS
    values[index % DIMENSIONS] = scale
    return values


def chunks(count: int, page: int | None = 1) -> list[Chunk]:
    return [Chunk(index=i, page_number=page, text=f"chunk number {i}") for i in range(count)]


@pytest.fixture
def scene(clean_db: str) -> Scene:
    return make_scene(clean_db)


def claim(url: str) -> ClaimedJob:
    with session_for(url) as session:
        job = IngestionJobRepository(session).claim(LEASE, 3)
        session.commit()
    assert job is not None
    return job


def complete(
    url: str,
    job: ClaimedJob,
    items: list[Chunk],
    vectors: list[list[float]],
    token: str | None = None,
) -> bool:
    with session_for(url) as session:
        accepted = IngestionJobRepository(session).complete(
            job.job_id, token or job.token, items, vectors
        )
        session.commit()
    return accepted


class TestSuccess:
    def test_chunks_count_status_and_bytes_change_together(self, scene: Scene) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)

        accepted = complete(scene.url, job, chunks(3), [vector(i) for i in range(3)])

        assert accepted is True
        state = document_state(scene.url, document)
        assert (state["status"], state["chunks_count"], state["error_code"]) == ("ready", 3, None)
        assert state["error_message"] is None
        assert chunk_count(scene.url, document) == 3
        job_after = job_state(scene.url, job_id)
        assert job_after["has_payload"] is False
        assert job_after["locked_by"] is None

    def test_each_chunk_keeps_its_index_page_text_and_the_subject_of_its_document(
        self, scene: Scene
    ) -> None:
        document, _ = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        items = [
            Chunk(index=0, page_number=3, text="first"),
            Chunk(index=1, page_number=3, text="second"),
            Chunk(index=2, page_number=None, text="third"),
        ]

        complete(scene.url, job, items, [vector(0), vector(1), vector(2)])

        rows = scalar(
            scene.url,
            "SELECT string_agg(chunk_index || ':' || coalesce(page_number::text, '-') || ':' "
            "|| content, ',' ORDER BY chunk_index) FROM document_chunks "
            "WHERE document_id = :d AND subject_id = :s",
            d=document,
            s=scene.subject,
        )
        assert rows == "0:3:first,1:3:second,2:-:third"

    def test_the_stored_embedding_is_the_validated_single_precision_value(
        self, scene: Scene
    ) -> None:
        document, _ = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        raw = [0.1] * DIMENSIONS

        complete(scene.url, job, chunks(1), [raw])

        stored = scalar(
            scene.url,
            "SELECT embedding::text FROM document_chunks WHERE document_id = :d",
            d=document,
        )
        expected = validate_embedding(raw)
        parsed = [float(part) for part in str(stored).strip("[]").split(",")]
        assert parsed == pytest.approx(expected, abs=1e-6)

    def test_nothing_is_visible_to_other_sessions_before_the_commit(self, scene: Scene) -> None:
        document, _ = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        with session_for(scene.url) as session:
            IngestionJobRepository(session).complete(
                job.job_id, job.token, chunks(2), [vector(0), vector(1)]
            )

            assert chunk_count(scene.url, document) == 0
            assert document_state(scene.url, document)["status"] == "processing"
            session.commit()

        assert chunk_count(scene.url, document) == 2

    def test_a_ready_document_can_be_found_by_its_owner_and_a_pending_one_cannot(
        self, scene: Scene
    ) -> None:
        document, _ = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        actor = SearchActor(user_id=scene.teacher, role=UserRole.TEACHER)

        def search() -> list[uuid.UUID]:
            with session_for(scene.url, role="app") as session:
                hits = ChunkRepository(session).find_similar(actor, scene.subject, vector(0), 5)
                return [hit.document_id for hit in hits]

        assert search() == []
        complete(scene.url, job, chunks(1), [vector(0)])

        assert search() == [document]


class TestAtomicity:
    def test_an_error_while_storing_leaves_no_chunk_and_no_status_change(
        self, scene: Scene
    ) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        items = [
            Chunk(index=0, page_number=1, text="fine"),
            Chunk(index=1, page_number=1, text="   "),  # blank: violates the content check
        ]

        with session_for(scene.url) as session:
            with pytest.raises(Exception) as caught:  # noqa: PT011 - the database error class
                IngestionJobRepository(session).complete(
                    job.job_id, job.token, items, [vector(0), vector(1)]
                )
                session.commit()
            session.rollback()

        assert "fine" not in str(caught.value)
        assert chunk_count(scene.url, document) == 0
        assert document_state(scene.url, document)["status"] == "processing"
        assert job_state(scene.url, job_id)["has_payload"] is True
        assert job_state(scene.url, job_id)["locked_by"] == job.token

    def test_the_job_can_still_be_failed_after_a_storing_error(self, scene: Scene) -> None:
        from app.models.ingestion import DocumentErrorCode

        document, _ = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        with session_for(scene.url) as session:
            with pytest.raises(Exception):  # noqa: B017, PT011
                IngestionJobRepository(session).complete(
                    job.job_id, job.token, [Chunk(0, 1, " ")], [vector(0)]
                )
            session.rollback()
        with session_for(scene.url) as session:
            assert IngestionJobRepository(session).mark_failed(
                job.job_id, job.token, DocumentErrorCode.PROCESSING_FAILED
            )
            session.commit()

        assert document_state(scene.url, document)["status"] == "failed"
        assert chunk_count(scene.url, document) == 0

    @pytest.mark.parametrize(
        "bad",
        [
            pytest.param([float("nan")] + [0.0] * (DIMENSIONS - 1), id="nan"),
            pytest.param([float("inf")] + [0.0] * (DIMENSIONS - 1), id="infinity"),
            pytest.param([0.0] * DIMENSIONS, id="zero-vector"),
            pytest.param([1.0] * (DIMENSIONS - 1), id="too-short"),
            pytest.param([1.0] * (DIMENSIONS + 1), id="too-long"),
            pytest.param([1e7] + [0.0] * (DIMENSIONS - 1), id="norm-out-of-range"),
        ],
    )
    def test_an_invalid_embedding_is_refused_before_anything_is_written(
        self, scene: Scene, bad: list[float]
    ) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)

        with session_for(scene.url) as session, pytest.raises(InvalidSearchInputError):
            IngestionJobRepository(session).complete(
                job.job_id, job.token, chunks(2), [vector(0), bad]
            )

        assert chunk_count(scene.url, document) == 0
        assert document_state(scene.url, document)["status"] == "processing"
        assert job_state(scene.url, job_id)["has_payload"] is True

    def test_a_document_without_chunks_cannot_become_ready(self, scene: Scene) -> None:
        document, _ = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)

        with session_for(scene.url) as session, pytest.raises(ValueError):  # noqa: PT011
            IngestionJobRepository(session).complete(job.job_id, job.token, [], [])

        assert document_state(scene.url, document)["status"] == "processing"

    @pytest.mark.parametrize(
        "indexes",
        [[1, 2], [0, 2], [0, 0], [1, 0]],
        ids=["from-one", "gap", "repeated", "unordered"],
    )
    def test_indexes_must_be_consecutive_from_zero(self, scene: Scene, indexes: list[int]) -> None:
        document, _ = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        items = [Chunk(index=i, page_number=1, text=f"t{i}") for i in indexes]

        with session_for(scene.url) as session, pytest.raises(ValueError):  # noqa: PT011
            IngestionJobRepository(session).complete(
                job.job_id, job.token, items, [vector(i) for i in range(len(items))]
            )

        assert chunk_count(scene.url, document) == 0

    def test_the_number_of_embeddings_must_match_the_number_of_chunks(self, scene: Scene) -> None:
        document, _ = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)

        with session_for(scene.url) as session, pytest.raises(ValueError):  # noqa: PT011
            IngestionJobRepository(session).complete(
                job.job_id, job.token, chunks(3), [vector(0), vector(1)]
            )

        assert chunk_count(scene.url, document) == 0

    @pytest.mark.parametrize(
        ("items", "vectors"),
        [
            pytest.param([], [], id="no-chunks"),
            pytest.param(chunks(3), [vector(0), vector(1)], id="fewer-embeddings"),
            pytest.param(
                [Chunk(index=1, page_number=1, text="x")], [vector(0)], id="indexes-from-one"
            ),
        ],
    )
    def test_invalid_input_is_refused_before_any_statement_runs(
        self, scene: Scene, items: list[Chunk], vectors: list[list[float]]
    ) -> None:
        insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        statements: list[str] = []
        with session_for(scene.url) as session:
            event.listen(
                session.get_bind(),
                "before_cursor_execute",
                lambda conn, cursor, statement, params, context, many: statements.append(statement),
            )
            with pytest.raises(ValueError):  # noqa: PT011
                IngestionJobRepository(session).complete(job.job_id, job.token, items, vectors)

        assert statements == []


class TestRetriesAndStaleWorkers:
    def test_a_retried_job_ends_with_exactly_one_set_of_chunks(self, scene: Scene) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        first = claim(scene.url)
        expire_lease(scene.url, job_id)
        second = claim(scene.url)

        assert complete(scene.url, second, chunks(2), [vector(0), vector(1)]) is True
        assert complete(scene.url, first, chunks(2), [vector(0), vector(1)]) is False

        assert chunk_count(scene.url, document) == 2
        assert document_state(scene.url, document)["chunks_count"] == 2

    def test_a_stale_token_stores_nothing_and_changes_no_status(self, scene: Scene) -> None:
        document, job_id = insert_pending(scene.url, scene.subject)
        stale = claim(scene.url)
        expire_lease(scene.url, job_id)
        claim(scene.url)

        assert complete(scene.url, stale, chunks(2), [vector(0), vector(1)]) is False

        assert chunk_count(scene.url, document) == 0
        assert document_state(scene.url, document)["status"] == "processing"

    def test_completing_twice_with_the_same_token_stores_one_set(self, scene: Scene) -> None:
        document, _ = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)

        assert complete(scene.url, job, chunks(2), [vector(0), vector(1)]) is True
        assert complete(scene.url, job, chunks(2), [vector(0), vector(1)]) is False

        assert chunk_count(scene.url, document) == 2

    def test_deleting_the_document_while_embeddings_are_computed_cancels_the_result(
        self, scene: Scene
    ) -> None:
        document, _ = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        run(scene.url, "DELETE FROM documents WHERE id = :d", d=document)

        assert complete(scene.url, job, chunks(2), [vector(0), vector(1)]) is False

        assert chunk_count(scene.url, document) == 0
        assert document_state(scene.url, document) == {}

    def test_a_delete_that_arrives_during_the_final_transaction_waits_and_then_wins(
        self, scene: Scene
    ) -> None:
        document, _ = insert_pending(scene.url, scene.subject)
        job = claim(scene.url)
        with session_for(scene.url) as session:
            IngestionJobRepository(session).complete(
                job.job_id, job.token, chunks(2), [vector(0), vector(1)]
            )
            # The delete from another session must wait for the open final transaction.
            with session_for(scene.url) as deleter:
                deleter.execute(text("SET LOCAL lock_timeout = '300ms'"))
                with pytest.raises(Exception):  # noqa: B017, PT011
                    deleter.execute(text("DELETE FROM documents WHERE id = :d"), {"d": document})
            session.commit()

        assert chunk_count(scene.url, document) == 2
