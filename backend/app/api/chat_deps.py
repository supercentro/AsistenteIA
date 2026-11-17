"""Dependency wiring for the /chat endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.repositories.chunk_repository import ChunkRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.enrollment_repository import EnrollmentRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.subject_repository import SubjectRepository
from app.repositories.user_repository import UserRepository
from app.services.llm_service import build_llm_service
from app.services.rag_service import RAGService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.config import Settings
    from app.rag.embedder import Embedder
    from app.services.llm_service import LLMService


def build_rag_service(
    *, db: Session, settings: Settings, embedder: Embedder, llm: LLMService | None = None
) -> RAGService:
    return RAGService(
        db=db,
        chunk_repo=ChunkRepository(db),
        embedder=embedder,
        llm=llm or build_llm_service(settings),
        user_repo=UserRepository(db),
        enrollment_repo=EnrollmentRepository(db),
        subject_repo=SubjectRepository(db),
        conversation_repo=ConversationRepository(db),
        message_repo=MessageRepository(db),
        settings=settings,
    )
