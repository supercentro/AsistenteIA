"""RAG service: the pipeline from question to grounded answer (design D3)."""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import IntegrityError

from app.core.errors import (
    ConsentRequiredError,
    ForbiddenError,
    NotFoundError,
    SearchUnavailableError,
    UnauthorizedError,
)
from app.core.security import TOKEN_ERROR_MESSAGE
from app.models.user import UserRole
from app.repositories.chunk_repository import ChunkRepository, ScoredChunk, SearchActor
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.enrollment_repository import EnrollmentRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.subject_repository import SubjectRepository
from app.repositories.user_repository import UserRepository
from app.services.consent_service import has_current_consent
from app.services.prompt_builder import build_prompt

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.config import Settings
    from app.rag.embedder import Embedder
    from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

# One embedding at a time: the local model is not guaranteed to be thread-safe, and the calls run in
# worker threads (never on the event loop).
_EMBED_LOCK = threading.Lock()

SNIPPET_MAX_LENGTH = 300
NO_MATERIAL_RESPONSE = (
    "No tengo material suficiente sobre este tema para responder tu pregunta. "
    "Consulta con tu profesor si necesitas más información."
)


@dataclass(frozen=True)
class SourceInfo:
    chunk_id: uuid.UUID | None
    document_id: uuid.UUID | None
    document_filename: str
    page_number: int | None
    rank: int
    score: float
    snippet: str


@dataclass(frozen=True)
class RetrievedContext:
    """What the read phase hands to the generation and persist phases: plain data, no session."""

    student_id: uuid.UUID
    subject_id: uuid.UUID
    message: str
    conversation_id: uuid.UUID | None
    history: list[dict[str, str]]
    chunks: list[ScoredChunk]


@dataclass(frozen=True)
class ChatResult:
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    answer: str
    sources: list[SourceInfo]
    no_material: bool


def _violated_foreign_key(error: IntegrityError) -> str | None:
    """Name of the constraint when PostgreSQL refused a foreign key (SQLSTATE 23503), else None.

    Anything else (a check, a unique key, a bug) is not a vanished row and must not become a 404.
    """
    if getattr(error.orig, "sqlstate", None) != "23503":
        return None
    return str(getattr(getattr(error.orig, "diag", None), "constraint_name", "") or "")


class RAGService:
    def __init__(
        self,
        db: Session,
        chunk_repo: ChunkRepository,
        embedder: Embedder,
        llm: LLMService,
        user_repo: UserRepository,
        enrollment_repo: EnrollmentRepository,
        subject_repo: SubjectRepository,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
        settings: Settings,
    ) -> None:
        self._db = db
        self._chunk_repo = chunk_repo
        self._embedder = embedder
        self._llm = llm
        self._user_repo = user_repo
        self._enrollment_repo = enrollment_repo
        self._subject_repo = subject_repo
        self._conversation_repo = conversation_repo
        self._message_repo = message_repo
        self._settings = settings

    @property
    def llm(self) -> LLMService:
        return self._llm

    def prepare(
        self,
        *,
        student_id: uuid.UUID,
        subject_id: uuid.UUID,
        message: str,
        conversation_id: uuid.UUID | None = None,
    ) -> RetrievedContext:
        """Read phase: authorization, history, embedding and retrieval. Synchronous; the caller
        closes the session afterwards so no connection is held while the LLM runs."""
        self._check_consent(student_id)
        self._check_enrollment(student_id, subject_id)
        self._resolve_conversation(student_id, subject_id, conversation_id)  # 404 if not visible
        # Give the connection back before embedding: a request queued on the embedding lock must
        # not sit on a pooled connection with a transaction open. Retrieval starts a new one.
        self._db.rollback()

        with _EMBED_LOCK:
            query_embedding = self._embedder.embed([message])[0]

        try:
            chunks = self._chunk_repo.find_similar(
                SearchActor(user_id=student_id, role=UserRole.STUDENT),
                subject_id,
                query_embedding,
                self._settings.chat_top_k,
            )
        except Exception:
            logger.warning("vector search failed")
            raise SearchUnavailableError() from None

        relevant = [c for c in chunks if c.similarity >= self._settings.chat_relevance_threshold]
        history = (
            self._load_history(conversation_id, student_id)
            if conversation_id is not None and relevant
            else []
        )
        return RetrievedContext(
            student_id=student_id,
            subject_id=subject_id,
            message=message,
            conversation_id=conversation_id,
            history=history,
            chunks=relevant,
        )

    async def generate(self, context: RetrievedContext) -> str:
        """Generation phase: only the LLM. Touches no repository and no session."""
        if not context.chunks:
            return NO_MATERIAL_RESPONSE
        chunk_dicts = [
            {
                "content": c.content,
                "filename": c.document_filename,
                "page_number": c.page_number,
            }
            for c in context.chunks
        ]
        prompt_messages = build_prompt(
            history=context.history,
            chunks=chunk_dicts,
            user_message=context.message,
            max_history=self._settings.chat_history_messages,
        )
        return await self._llm.generate(prompt_messages[0]["content"], prompt_messages[1:])

    def persist(self, context: RetrievedContext, answer_text: str) -> ChatResult:
        """Persist phase, in a new transaction: revalidate, then write the turn atomically.

        Consent, enrollment, the conversation and the cited chunks may all have changed while the
        LLM ran. The caller commits explicitly before it builds the HTTP response.
        """
        # First statement of the transaction: an unenrolment of this student in this subject
        # either finished before we look at the enrollment or waits until we commit.
        self._enrollment_repo.lock_student_subject(context.student_id, context.subject_id)
        self._check_consent(context.student_id)
        self._check_enrollment(context.student_id, context.subject_id)
        conversation = self._resolve_conversation(
            context.student_id, context.subject_id, context.conversation_id
        )
        try:
            conversation = conversation or self._conversation_repo.create(
                student_id=context.student_id, subject_id=context.subject_id
            )
        except IntegrityError as error:
            if _violated_foreign_key(error) is None:
                raise
            raise NotFoundError("Subject not found") from None

        # The first attempt keeps the chunk ids; if a cited chunk was deleted meanwhile the foreign
        # key refuses it and the sources are stored without them (filename and page remain). A
        # second failure means the conversation itself is gone.
        for keep_chunk_ids in (True, False):
            try:
                with self._db.begin_nested():
                    return self._write_turn(conversation, context, answer_text, keep_chunk_ids)
            except IntegrityError as error:
                constraint = _violated_foreign_key(error)
                if constraint is None:
                    raise
                if keep_chunk_ids and "chunk_id" in constraint:
                    continue
                break
        raise NotFoundError("Conversation not found")

    def _write_turn(
        self, conversation: Any, context: RetrievedContext, answer_text: str, keep_chunk_ids: bool
    ) -> ChatResult:
        self._message_repo.create_with_sources(
            conversation_id=conversation.id,
            role="user",
            content=context.message,
            sources=[],
        )
        assistant_msg = self._message_repo.create_with_sources(
            conversation_id=conversation.id,
            role="assistant",
            content=answer_text,
            sources=[
                {
                    "chunk_id": c.chunk_id if keep_chunk_ids else None,
                    "document_filename": c.document_filename,
                    "page_number": c.page_number,
                    "rank": rank + 1,
                    "score": c.similarity,
                }
                for rank, c in enumerate(context.chunks)
            ],
        )
        return ChatResult(
            conversation_id=conversation.id,
            message_id=assistant_msg.id,
            answer=answer_text,
            sources=[
                SourceInfo(
                    chunk_id=c.chunk_id if keep_chunk_ids else None,
                    document_id=c.document_id if keep_chunk_ids else None,
                    document_filename=c.document_filename,
                    page_number=c.page_number,
                    rank=rank + 1,
                    score=c.similarity,
                    snippet=c.content[:SNIPPET_MAX_LENGTH] if keep_chunk_ids else "",
                )
                for rank, c in enumerate(context.chunks)
            ],
            no_material=not context.chunks,
        )

    def _check_consent(self, student_id: uuid.UUID) -> None:
        user = self._user_repo.get_by_id(student_id)
        if user is None:
            raise UnauthorizedError(TOKEN_ERROR_MESSAGE, headers={"WWW-Authenticate": "Bearer"})
        if not has_current_consent(user, self._settings):
            raise ConsentRequiredError()

    def _check_enrollment(self, student_id: uuid.UUID, subject_id: uuid.UUID) -> None:
        if self._enrollment_repo.is_enrolled(student_id=student_id, subject_id=subject_id):
            return
        if not self._subject_repo.subject_exists(subject_id):
            raise NotFoundError("Subject not found")
        raise ForbiddenError("Student is not enrolled in the subject")

    def _load_history(
        self, conversation_id: uuid.UUID, student_id: uuid.UUID
    ) -> list[dict[str, str]]:
        limit = self._settings.chat_history_messages
        if limit <= 0:
            return []
        messages = self._message_repo.recent_for_prompt(conversation_id, student_id, limit)
        return [{"role": m.role.value, "content": m.content} for m in messages]

    def _resolve_conversation(
        self,
        student_id: uuid.UUID,
        subject_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
    ) -> Any:
        if conversation_id is None:
            return None
        conv = self._conversation_repo.get_by_id_and_student(
            conversation_id, student_id, subject_id=subject_id
        )
        if conv is None:
            raise NotFoundError("Conversation not found")
        return conv
