"""POST /chat — ask the assistant a question (role student, enrolled, consent)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import (
    AppEmbedder,
    AppSettings,
    DbSession,
    enforce_chat_rate_limit,
    require_student,
)
from app.api.transaction import commit_or_rollback
from app.core.config import Settings
from app.models.user import User
from app.rag.embedder import Embedder
from app.schemas.chat import ChatRequest, ChatResponse, SourceSchema
from app.services.llm_service import LLMService
from app.services.rag_service import ChatResult, RAGService, RetrievedContext

router = APIRouter(tags=["Chat"])


def _read_phase(
    service: RAGService, db: Session, student_id: uuid.UUID, body: ChatRequest
) -> RetrievedContext:
    """Authorization, history, embedding and retrieval; the session is closed afterwards so that
    its connection goes back to the pool before the (slow, external) LLM call."""
    try:
        return service.prepare(
            student_id=student_id,
            subject_id=body.subject_id,
            message=body.message,
            conversation_id=body.conversation_id,
        )
    finally:
        db.close()


def _persist_phase(
    factory: sessionmaker[Session],
    settings: Settings,
    embedder: Embedder,
    llm: LLMService,
    context: RetrievedContext,
    answer_text: str,
) -> ChatResult:
    """A new transaction: revalidate, write the turn atomically, commit before answering."""
    from app.api.chat_deps import build_rag_service

    session = factory()
    try:
        service: RAGService = build_rag_service(
            db=session, settings=settings, embedder=embedder, llm=llm
        )
        result = service.persist(context, answer_text)
        commit_or_rollback(session)
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(enforce_chat_rate_limit)])
async def ask_question(
    request: Request,
    body: ChatRequest,
    student: Annotated[User, Depends(require_student)],
    db: DbSession,
    settings: AppSettings,
    embedder: AppEmbedder,
) -> ChatResponse:
    from app.api.chat_deps import build_rag_service

    service = build_rag_service(db=db, settings=settings, embedder=embedder)
    context = await run_in_threadpool(_read_phase, service, db, student.id, body)
    answer_text = await service.generate(context)  # no database session is open here
    result = await run_in_threadpool(
        _persist_phase,
        request.app.state.session_factory,
        settings,
        embedder,
        service.llm,
        context,
        answer_text,
    )
    return ChatResponse(
        conversation_id=result.conversation_id,
        message_id=result.message_id,
        answer=result.answer,
        no_material=result.no_material,
        sources=[
            SourceSchema(
                chunk_id=s.chunk_id,
                document_id=s.document_id,
                filename=s.document_filename,
                page_number=s.page_number,
                rank=s.rank,
                snippet=s.snippet,
            )
            for s in result.sources
        ],
    )
