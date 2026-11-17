"""Unit tests for RAGService with mocked dependencies (task 6.1)."""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import (
    ConsentRequiredError,
    ForbiddenError,
    LLMBlockedError,
    LLMUnavailableError,
    NotFoundError,
    SearchUnavailableError,
)
from app.repositories.chunk_repository import ScoredChunk


def _make_chunk(
    *,
    similarity: float = 0.8,
    content: str = "Photosynthesis uses sunlight.",
    filename: str = "bio.pdf",
    page_number: int | None = 5,
) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_filename=filename,
        chunk_index=0,
        page_number=page_number,
        content=content,
        similarity=similarity,
    )


def _build_service(
    *,
    chunks: list[ScoredChunk] | None = None,
    llm_response: str = "LLM says: answer",
    llm_side_effect: Exception | None = None,
    search_side_effect: Exception | None = None,
    consent_version: str | None = "1.0",
    required_consent: str = "1.0",
    is_enrolled: bool = True,
    subject_exists: bool = True,
) -> tuple[Any, dict[str, Any]]:
    from app.services.rag_service import RAGService

    mock_db = MagicMock()
    mock_db.begin_nested.return_value.__exit__.return_value = False

    mock_chunk_repo = MagicMock()
    if search_side_effect:
        mock_chunk_repo.find_similar.side_effect = search_side_effect
    else:
        mock_chunk_repo.find_similar.return_value = (
            chunks if chunks is not None else [_make_chunk()]
        )

    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = [[0.1] * 384]

    mock_llm = AsyncMock()
    if llm_side_effect:
        mock_llm.generate.side_effect = llm_side_effect
    else:
        mock_llm.generate.return_value = llm_response

    mock_user_repo = MagicMock()
    user = MagicMock()
    user.consent_version = consent_version
    mock_user_repo.get_by_id.return_value = user

    mock_enrollment_repo = MagicMock()
    mock_enrollment_repo.is_enrolled.return_value = is_enrolled

    mock_subject_repo = MagicMock()
    mock_subject_repo.subject_exists.return_value = subject_exists

    mock_conversation_repo = MagicMock()
    mock_conversation_repo.create.return_value = MagicMock(id=uuid.uuid4())

    mock_message_repo = MagicMock()
    mock_message_repo.create_with_sources.return_value = MagicMock(id=uuid.uuid4())

    settings = MagicMock()
    settings.chat_top_k = 5
    settings.chat_relevance_threshold = 0.3
    settings.chat_history_messages = 10
    settings.privacy_policy_version = required_consent

    service = RAGService(
        db=mock_db,
        chunk_repo=mock_chunk_repo,
        embedder=mock_embedder,
        llm=mock_llm,
        user_repo=mock_user_repo,
        enrollment_repo=mock_enrollment_repo,
        subject_repo=mock_subject_repo,
        conversation_repo=mock_conversation_repo,
        message_repo=mock_message_repo,
        settings=settings,
    )
    return service, {
        "db": mock_db,
        "chunk_repo": mock_chunk_repo,
        "embedder": mock_embedder,
        "llm": mock_llm,
        "user_repo": mock_user_repo,
        "enrollment_repo": mock_enrollment_repo,
        "subject_repo": mock_subject_repo,
        "conversation_repo": mock_conversation_repo,
        "message_repo": mock_message_repo,
    }


async def _answer(service: Any, **kwargs: Any) -> Any:
    """The three phases in sequence, as the endpoint runs them (session closed in between)."""
    context = service.prepare(**kwargs)
    text = await service.generate(context)
    return service.persist(context, text)


# --- happy path ---


@pytest.mark.asyncio
async def test_happy_path_returns_answer_with_sources() -> None:
    chunk = _make_chunk(similarity=0.8)
    service, mocks = _build_service(chunks=[chunk], llm_response="The answer is photosynthesis.")

    result = await _answer(
        service,
        student_id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        message="What is photosynthesis?",
    )

    assert result.answer == "The answer is photosynthesis."
    assert result.no_material is False
    assert len(result.sources) == 1
    assert result.sources[0].document_filename == "bio.pdf"
    assert result.conversation_id is not None
    assert result.message_id is not None
    mocks["llm"].generate.assert_awaited_once()


# --- no material ---


@pytest.mark.asyncio
async def test_no_material_when_all_below_threshold() -> None:
    chunk = _make_chunk(similarity=0.1)
    service, mocks = _build_service(chunks=[chunk])

    result = await _answer(
        service,
        student_id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        message="Unrelated question",
    )

    assert result.no_material is True
    assert result.sources == []
    mocks["llm"].generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_material_when_no_chunks_returned() -> None:
    service, mocks = _build_service(chunks=[])

    result = await _answer(
        service,
        student_id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        message="Anything",
    )

    assert result.no_material is True
    mocks["llm"].generate.assert_not_awaited()


# --- consent check ---


@pytest.mark.asyncio
async def test_missing_consent_raises_consent_required() -> None:
    service, _ = _build_service(consent_version=None)

    with pytest.raises(ConsentRequiredError):
        await _answer(
            service,
            student_id=uuid.uuid4(),
            subject_id=uuid.uuid4(),
            message="test",
        )


@pytest.mark.asyncio
async def test_outdated_consent_raises_consent_required() -> None:
    service, _ = _build_service(consent_version="0.9", required_consent="1.0")

    with pytest.raises(ConsentRequiredError):
        await _answer(
            service,
            student_id=uuid.uuid4(),
            subject_id=uuid.uuid4(),
            message="test",
        )


# --- enrollment check ---


@pytest.mark.asyncio
async def test_not_enrolled_in_an_existing_subject_raises_forbidden() -> None:
    service, mocks = _build_service(is_enrolled=False, subject_exists=True)

    with pytest.raises(ForbiddenError) as caught:
        await _answer(service, student_id=uuid.uuid4(), subject_id=uuid.uuid4(), message="hello")

    assert caught.value.status_code == 403
    mocks["embedder"].embed.assert_not_called()
    mocks["llm"].generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_subject_raises_not_found() -> None:
    service, mocks = _build_service(is_enrolled=False, subject_exists=False)

    with pytest.raises(NotFoundError):
        await _answer(service, student_id=uuid.uuid4(), subject_id=uuid.uuid4(), message="hello")

    mocks["llm"].generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_llm_timeout_raises_llm_unavailable() -> None:
    service, _ = _build_service(llm_side_effect=LLMUnavailableError())

    with pytest.raises(LLMUnavailableError):
        await _answer(
            service,
            student_id=uuid.uuid4(),
            subject_id=uuid.uuid4(),
            message="test",
        )


@pytest.mark.asyncio
async def test_llm_safety_block_raises_llm_blocked() -> None:
    service, _ = _build_service(llm_side_effect=LLMBlockedError())

    with pytest.raises(LLMBlockedError):
        await _answer(
            service,
            student_id=uuid.uuid4(),
            subject_id=uuid.uuid4(),
            message="test",
        )


# --- search failure ---


@pytest.mark.asyncio
async def test_search_failure_raises_search_unavailable() -> None:
    service, _ = _build_service(search_side_effect=Exception("DB connection lost"))

    with pytest.raises(SearchUnavailableError):
        await _answer(
            service,
            student_id=uuid.uuid4(),
            subject_id=uuid.uuid4(),
            message="test",
        )


# --- source snippet truncation (task 6.3) ---


@pytest.mark.asyncio
async def test_source_snippets_capped_at_300_chars() -> None:
    long_content = "A" * 500
    chunk = _make_chunk(content=long_content, similarity=0.8)
    service, _ = _build_service(chunks=[chunk])

    result = await _answer(
        service,
        student_id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        message="test",
    )

    assert len(result.sources[0].snippet) <= 300


# --- conversation binding and history (adversarial review findings 1 and 2) ---


@pytest.mark.asyncio
async def test_foreign_conversation_is_rejected_before_embedding_or_llm() -> None:
    service, mocks = _build_service()
    mocks["conversation_repo"].get_by_id_and_student.return_value = None

    with pytest.raises(NotFoundError):
        await _answer(
            service,
            student_id=uuid.uuid4(),
            subject_id=uuid.uuid4(),
            message="hello",
            conversation_id=uuid.uuid4(),
        )

    mocks["embedder"].embed.assert_not_called()
    mocks["llm"].generate.assert_not_awaited()
    mocks["message_repo"].create_with_sources.assert_not_called()


@pytest.mark.asyncio
async def test_conversation_lookup_is_bound_to_the_subject() -> None:
    service, mocks = _build_service()
    student_id, subject_id, conversation_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    mocks["message_repo"].recent_for_prompt.return_value = []

    await _answer(
        service,
        student_id=student_id,
        subject_id=subject_id,
        message="hello",
        conversation_id=conversation_id,
    )

    assert (
        mocks["conversation_repo"].get_by_id_and_student.call_args_list
        == [((conversation_id, student_id), {"subject_id": subject_id})] * 2
    )  # once to read, once more to revalidate before writing


@pytest.mark.asyncio
async def test_previous_messages_reach_the_llm() -> None:
    service, mocks = _build_service()
    earlier = [
        MagicMock(role=MagicMock(value="user"), content="first question"),
        MagicMock(role=MagicMock(value="assistant"), content="first answer"),
    ]
    mocks["message_repo"].recent_for_prompt.return_value = earlier

    await _answer(
        service,
        student_id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        message="follow-up",
        conversation_id=uuid.uuid4(),
    )

    sent = mocks["llm"].generate.await_args.args[1]
    assert [m["content"] for m in sent] == ["first question", "first answer", "follow-up"]
    assert [m["role"] for m in sent] == ["user", "assistant", "user"]


@pytest.mark.asyncio
async def test_history_is_read_with_the_configured_window_only() -> None:
    service, mocks = _build_service()
    student_id, conversation_id = uuid.uuid4(), uuid.uuid4()
    mocks["message_repo"].recent_for_prompt.return_value = []

    await _answer(
        service,
        student_id=student_id,
        subject_id=uuid.uuid4(),
        message="follow-up",
        conversation_id=conversation_id,
    )

    limit = service._settings.chat_history_messages
    mocks["message_repo"].recent_for_prompt.assert_called_once_with(
        conversation_id, student_id, limit
    )
    mocks["message_repo"].list_by_conversation.assert_not_called()


@pytest.mark.asyncio
async def test_history_is_not_read_when_the_window_is_zero() -> None:
    service, mocks = _build_service()
    service._settings.chat_history_messages = 0

    await _answer(
        service,
        student_id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        message="follow-up",
        conversation_id=uuid.uuid4(),
    )

    mocks["message_repo"].recent_for_prompt.assert_not_called()
    mocks["message_repo"].list_by_conversation.assert_not_called()


# --- request phases (design D3): no session during generation, revalidation before writing ---

from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.core.errors import UnauthorizedError  # noqa: E402


class _PgError(Exception):
    """What psycopg raises under an IntegrityError: a SQLSTATE and the violated constraint."""

    def __init__(self, sqlstate: str, constraint: str = "") -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate
        self.diag = MagicMock(constraint_name=constraint)


def _integrity(sqlstate: str, constraint: str = "") -> IntegrityError:
    return IntegrityError("insert", {}, _PgError(sqlstate, constraint))


def _prepared(**options: Any) -> tuple[Any, dict[str, Any], Any]:
    service, mocks = _build_service(**options)
    context = service.prepare(
        student_id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        message="What is photosynthesis?",
        conversation_id=None,
    )
    return service, mocks, context


def _reset_calls(mocks: dict[str, Any]) -> None:
    for mock in mocks.values():
        mock.reset_mock()


@pytest.mark.asyncio
async def test_generate_touches_no_repository_and_no_session() -> None:
    service, mocks, context = _prepared()
    _reset_calls(mocks)
    mocks["llm"].generate.return_value = "text"

    assert await service.generate(context) == "text"

    for name in ("db", "chunk_repo", "user_repo", "enrollment_repo", "subject_repo"):
        assert mocks[name].method_calls == [], name
    assert mocks["conversation_repo"].method_calls == []
    assert mocks["message_repo"].method_calls == []


@pytest.mark.asyncio
async def test_generate_without_relevant_chunks_does_not_call_the_llm() -> None:
    service, mocks, context = _prepared(chunks=[_make_chunk(similarity=0.01)])

    text = await service.generate(context)

    assert "No tengo material" in text
    mocks["llm"].generate.assert_not_awaited()


def test_persist_revalidates_consent() -> None:
    service, mocks, context = _prepared()
    mocks["user_repo"].get_by_id.return_value.consent_version = "0.9"

    with pytest.raises(ConsentRequiredError):
        service.persist(context, "answer")

    mocks["message_repo"].create_with_sources.assert_not_called()


def test_persist_revalidates_enrollment() -> None:
    service, mocks, context = _prepared()
    mocks["enrollment_repo"].is_enrolled.return_value = False

    with pytest.raises(ForbiddenError):
        service.persist(context, "answer")

    mocks["message_repo"].create_with_sources.assert_not_called()


def test_persist_reports_a_deleted_subject_as_not_found() -> None:
    service, mocks, context = _prepared()
    mocks["enrollment_repo"].is_enrolled.return_value = False
    mocks["subject_repo"].subject_exists.return_value = False

    with pytest.raises(NotFoundError):
        service.persist(context, "answer")

    mocks["message_repo"].create_with_sources.assert_not_called()


def test_persist_rejects_a_conversation_deleted_during_generation() -> None:
    service, mocks = _build_service()
    context = service.prepare(
        student_id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        message="hello",
        conversation_id=uuid.uuid4(),
    )
    mocks["message_repo"].recent_for_prompt.return_value = []
    mocks["conversation_repo"].get_by_id_and_student.return_value = None  # gone meanwhile

    with pytest.raises(NotFoundError):
        service.persist(context, "answer")

    mocks["message_repo"].create_with_sources.assert_not_called()


def test_persist_rejects_a_user_deleted_during_generation() -> None:
    service, mocks, context = _prepared()
    mocks["user_repo"].get_by_id.return_value = None

    with pytest.raises(UnauthorizedError):
        service.persist(context, "answer")


def test_a_cited_chunk_deleted_meanwhile_is_stored_without_its_chunk_id() -> None:
    chunk = _make_chunk()
    service, mocks, context = _prepared(chunks=[chunk])
    stored = []

    def create(**kwargs: Any) -> Any:
        stored.append(kwargs)
        if kwargs["role"] == "assistant" and kwargs["sources"][0]["chunk_id"] is not None:
            raise _integrity("23503", "message_sources_chunk_id_fkey")
        return MagicMock(id=uuid.uuid4())

    mocks["message_repo"].create_with_sources.side_effect = create

    result = service.persist(context, "answer")

    assert result.sources[0].chunk_id is None and result.sources[0].document_id is None
    assert result.sources[0].document_filename == "bio.pdf"
    assert result.sources[0].snippet == ""  # no document text once the chunk is gone
    assert stored[-1]["sources"][0]["chunk_id"] is None
    assert stored[-1]["sources"][0]["document_filename"] == "bio.pdf"


def test_persist_gives_up_with_not_found_when_the_conversation_vanishes_mid_write() -> None:
    service, mocks, context = _prepared()
    mocks["message_repo"].create_with_sources.side_effect = _integrity(
        "23503", "messages_conversation_id_fkey"
    )

    with pytest.raises(NotFoundError):
        service.persist(context, "answer")


def test_an_integrity_error_that_is_not_a_foreign_key_is_not_hidden_as_a_404() -> None:
    service, mocks, context = _prepared()
    mocks["message_repo"].create_with_sources.side_effect = _integrity("23514", "some_check")

    with pytest.raises(IntegrityError):
        service.persist(context, "answer")


def test_a_conversation_create_that_violates_a_foreign_key_is_a_404_other_errors_are_not() -> None:
    service, mocks, context = _prepared()
    mocks["conversation_repo"].create.side_effect = _integrity(
        "23503", "conversations_subject_id_fkey"
    )
    with pytest.raises(NotFoundError):
        service.persist(context, "answer")

    mocks["conversation_repo"].create.side_effect = _integrity("23514", "some_check")
    with pytest.raises(IntegrityError):
        service.persist(context, "answer")


def test_prepare_ends_the_read_transaction_before_it_embeds() -> None:
    service, mocks = _build_service()
    order: list[str] = []
    mocks["db"].rollback.side_effect = lambda: order.append("end-transaction")

    def embed(texts: Any) -> list[list[float]]:
        order.append("embed")
        return [[0.1] * 384]

    mocks["embedder"].embed.side_effect = embed

    service.prepare(student_id=uuid.uuid4(), subject_id=uuid.uuid4(), message="hello")

    assert order == ["end-transaction", "embed"]


# --- M2: the advisory lock is the first thing persist does, and only persist takes it ---


def test_persist_takes_the_enrollment_lock_first_and_exactly_once() -> None:
    service, mocks, context = _prepared()
    order: list[str] = []
    user = MagicMock(consent_version="1.0")

    def locked(*args: Any) -> None:
        order.append("lock")

    def consent(*args: Any) -> Any:
        order.append("consent")
        return user

    def enrolled(**kwargs: Any) -> bool:
        order.append("enrolled")
        return True

    mocks["enrollment_repo"].lock_student_subject.side_effect = locked
    mocks["user_repo"].get_by_id.side_effect = consent
    mocks["enrollment_repo"].is_enrolled.side_effect = enrolled

    service.persist(context, "answer")

    assert order[:3] == ["lock", "consent", "enrolled"]
    assert order.count("lock") == 1
    mocks["enrollment_repo"].lock_student_subject.assert_called_once_with(
        context.student_id, context.subject_id
    )


@pytest.mark.asyncio
async def test_the_read_and_generation_phases_take_no_lock() -> None:
    service, mocks, context = _prepared()  # runs `prepare`
    mocks["enrollment_repo"].lock_student_subject.assert_not_called()

    await service.generate(context)

    mocks["enrollment_repo"].lock_student_subject.assert_not_called()


# --- citation attribution (design D5b, task 18.1) ---


def _three_chunks() -> list[ScoredChunk]:
    return [
        _make_chunk(similarity=0.9, filename="a.pdf", page_number=1, content="alpha"),
        _make_chunk(similarity=0.8, filename="b.pdf", page_number=2, content="beta"),
        _make_chunk(similarity=0.7, filename="c.pdf", page_number=3, content="gamma"),
    ]


@pytest.mark.asyncio
async def test_only_the_cited_chunks_are_returned_and_stored_with_their_retrieval_rank() -> None:
    service, mocks = _build_service(chunks=_three_chunks(), llm_response="It is beta [2].")

    result = await _answer(service, student_id=uuid.uuid4(), subject_id=uuid.uuid4(), message="q")

    assert [(s.rank, s.document_filename) for s in result.sources] == [(2, "b.pdf")]
    stored = mocks["message_repo"].create_with_sources.call_args_list[-1].kwargs["sources"]
    assert [(s["rank"], s["document_filename"]) for s in stored] == [(2, "b.pdf")]
    assert result.sources[0].snippet == "beta"


@pytest.mark.asyncio
async def test_two_cited_chunks_keep_rank_order_whatever_the_citation_order() -> None:
    service, _ = _build_service(chunks=_three_chunks(), llm_response="[3] then [1].")

    result = await _answer(service, student_id=uuid.uuid4(), subject_id=uuid.uuid4(), message="q")

    assert [s.rank for s in result.sources] == [1, 3]


@pytest.mark.asyncio
async def test_an_answer_without_a_valid_marker_keeps_every_retrieved_chunk() -> None:
    service, mocks = _build_service(chunks=_three_chunks(), llm_response="See [9] and [0].")

    result = await _answer(service, student_id=uuid.uuid4(), subject_id=uuid.uuid4(), message="q")

    assert [s.rank for s in result.sources] == [1, 2, 3]
    stored = mocks["message_repo"].create_with_sources.call_args_list[-1].kwargs["sources"]
    assert [s["rank"] for s in stored] == [1, 2, 3]


@pytest.mark.asyncio
async def test_the_no_material_answer_has_no_sources_whatever_it_contains() -> None:
    service, mocks = _build_service(chunks=[])

    result = await _answer(service, student_id=uuid.uuid4(), subject_id=uuid.uuid4(), message="q")

    assert result.sources == []
    assert result.no_material is True
