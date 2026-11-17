"""Unit tests for conversation SQLAlchemy models (task 3.1).

Verify column types, constraints, foreign keys, cascades and indexes
declared in `models/conversation.py` against `docs/data-model.md`.
"""

from typing import Any

from sqlalchemy import inspect

from app.core.database import Base


def _import_models() -> tuple[Any, Any, Any, Any]:
    from app.models.conversation import (
        Conversation,
        Message,
        MessageRole,
        MessageSource,
    )

    return Conversation, Message, MessageRole, MessageSource


def test_conversation_model_imports() -> None:
    Conversation, Message, MessageRole, MessageSource = _import_models()
    assert Conversation.__tablename__ == "conversations"
    assert Message.__tablename__ == "messages"
    assert MessageSource.__tablename__ == "message_sources"


def test_message_role_enum_values() -> None:
    _, _, MessageRole, _ = _import_models()
    assert MessageRole.USER.value == "user"
    assert MessageRole.ASSISTANT.value == "assistant"
    assert len(MessageRole) == 2


# --- Conversation columns ---


def test_conversation_has_expected_columns() -> None:
    Conversation, _, _, _ = _import_models()
    table = Conversation.__table__
    col_names = {c.name for c in table.columns}
    assert col_names == {"id", "student_id", "subject_id", "created_at"}


def test_conversation_id_is_uuid_pk() -> None:
    Conversation, _, _, _ = _import_models()
    col = Conversation.__table__.c.id
    assert col.primary_key
    assert col.server_default is not None


def test_conversation_student_id_is_fk_to_users() -> None:
    Conversation, _, _, _ = _import_models()
    col = Conversation.__table__.c.student_id
    assert not col.nullable
    fk = next(iter(col.foreign_keys))
    assert fk.target_fullname == "users.id"


def test_conversation_subject_id_is_fk_to_subjects() -> None:
    Conversation, _, _, _ = _import_models()
    col = Conversation.__table__.c.subject_id
    assert not col.nullable
    fk = next(iter(col.foreign_keys))
    assert fk.target_fullname == "subjects.id"


def test_conversation_cascade_on_delete_student() -> None:
    Conversation, _, _, _ = _import_models()
    fk = next(fk for fk in Conversation.__table__.c.student_id.foreign_keys)
    assert fk.ondelete and fk.ondelete.upper() == "CASCADE"


def test_conversation_cascade_on_delete_subject() -> None:
    Conversation, _, _, _ = _import_models()
    fk = next(fk for fk in Conversation.__table__.c.subject_id.foreign_keys)
    assert fk.ondelete and fk.ondelete.upper() == "CASCADE"


def test_conversation_has_composite_index() -> None:
    Conversation, _, _, _ = _import_models()
    table = Conversation.__table__
    index_cols_sets = [tuple(c.name for c in idx.columns) for idx in table.indexes]
    assert ("student_id", "subject_id", "created_at") in index_cols_sets


def test_conversation_created_at_has_timezone() -> None:
    Conversation, _, _, _ = _import_models()
    col = Conversation.__table__.c.created_at
    assert not col.nullable
    assert col.type.timezone is True


# --- Message columns ---


def test_message_has_expected_columns() -> None:
    _, Message, _, _ = _import_models()
    table = Message.__table__
    col_names = {c.name for c in table.columns}
    assert col_names == {"id", "conversation_id", "role", "content", "created_at"}


def test_message_conversation_fk_cascade() -> None:
    _, Message, _, _ = _import_models()
    fk = next(fk for fk in Message.__table__.c.conversation_id.foreign_keys)
    assert fk.target_fullname == "conversations.id"
    assert fk.ondelete and fk.ondelete.upper() == "CASCADE"


def test_message_role_is_enum() -> None:
    _, Message, MessageRole, _ = _import_models()
    col = Message.__table__.c.role
    assert not col.nullable
    enum_values = col.type.enums
    assert "user" in enum_values
    assert "assistant" in enum_values


# --- MessageSource columns ---


def test_message_source_has_expected_columns() -> None:
    _, _, _, MessageSource = _import_models()
    table = MessageSource.__table__
    col_names = {c.name for c in table.columns}
    assert col_names == {
        "id",
        "message_id",
        "chunk_id",
        "document_filename",
        "page_number",
        "rank",
        "score",
    }


def test_message_source_message_fk_cascade() -> None:
    _, _, _, MessageSource = _import_models()
    fk = next(fk for fk in MessageSource.__table__.c.message_id.foreign_keys)
    assert fk.target_fullname == "messages.id"
    assert fk.ondelete and fk.ondelete.upper() == "CASCADE"


def test_message_source_chunk_fk_set_null() -> None:
    _, _, _, MessageSource = _import_models()
    fk = next(fk for fk in MessageSource.__table__.c.chunk_id.foreign_keys)
    assert fk.target_fullname == "document_chunks.id"
    assert fk.ondelete and fk.ondelete.upper() == "SET NULL"


def test_message_source_chunk_id_nullable() -> None:
    _, _, _, MessageSource = _import_models()
    col = MessageSource.__table__.c.chunk_id
    assert col.nullable


def test_message_source_document_filename_not_nullable() -> None:
    _, _, _, MessageSource = _import_models()
    col = MessageSource.__table__.c.document_filename
    assert not col.nullable


def test_message_source_page_number_nullable() -> None:
    _, _, _, MessageSource = _import_models()
    col = MessageSource.__table__.c.page_number
    assert col.nullable


def test_message_source_rank_not_nullable() -> None:
    _, _, _, MessageSource = _import_models()
    col = MessageSource.__table__.c.rank
    assert not col.nullable


def test_message_source_score_not_nullable() -> None:
    _, _, _, MessageSource = _import_models()
    col = MessageSource.__table__.c.score
    assert not col.nullable


# --- Relationships ---


def test_conversation_has_messages_relationship() -> None:
    Conversation, _, _, _ = _import_models()
    mapper = inspect(Conversation)
    assert "messages" in mapper.relationships


def test_message_has_sources_relationship() -> None:
    _, Message, _, _ = _import_models()
    mapper = inspect(Message)
    assert "sources" in mapper.relationships


# --- Models registered on Base metadata ---


def test_conversation_tables_are_on_base_metadata() -> None:
    _import_models()
    table_names = set(Base.metadata.tables.keys())
    assert "conversations" in table_names
    assert "messages" in table_names
    assert "message_sources" in table_names
