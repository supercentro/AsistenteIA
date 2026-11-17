"""Conversation endpoints: list, messages, delete one, delete all."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import DbSession, require_student
from app.api.transaction import commit_or_rollback
from app.core.errors import NotFoundError
from app.models.user import User
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.chat import SourceSchema
from app.schemas.conversation import ConversationResponse, MessageResponse

SNIPPET_MAX_LENGTH = 300

router = APIRouter(prefix="/conversations", tags=["Conversations"])

Student = Annotated[User, Depends(require_student)]


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    student: Student,
    db: DbSession,
    subject_id: uuid.UUID | None = None,
) -> list[ConversationResponse]:
    repo = ConversationRepository(db)
    conversations = repo.list_by_student(student.id, subject_id=subject_id)
    return [ConversationResponse.model_validate(c) for c in conversations]


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def get_messages(
    conversation_id: uuid.UUID,
    student: Student,
    db: DbSession,
) -> list[MessageResponse]:
    if ConversationRepository(db).get_visible_to_student(conversation_id, student.id) is None:
        raise NotFoundError("Conversation not found")
    msg_repo = MessageRepository(db)
    messages = msg_repo.list_by_conversation(conversation_id, student.id)
    details = msg_repo.citation_details(conversation_id, student.id)
    return [
        MessageResponse(
            id=m.id,
            role=m.role.value,
            content=m.content,
            created_at=m.created_at,
            sources=[
                SourceSchema(
                    chunk_id=s.chunk_id,
                    document_id=details[s.chunk_id][0] if s.chunk_id in details else None,
                    filename=s.document_filename,
                    page_number=s.page_number,
                    rank=s.rank,
                    snippet=details[s.chunk_id][1][:SNIPPET_MAX_LENGTH]
                    if s.chunk_id in details
                    else "",
                )
                for s in sorted(m.sources, key=lambda source: source.rank)
            ],
        )
        for m in messages
    ]


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: uuid.UUID,
    student: Student,
    db: DbSession,
) -> Response:
    repo = ConversationRepository(db)
    if not repo.delete_by_id_and_student(conversation_id, student.id):
        raise NotFoundError("Conversation not found")
    commit_or_rollback(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
