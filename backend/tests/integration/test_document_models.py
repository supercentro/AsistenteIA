"""ORM models `Document` and `DocumentChunk` against the migrated test database."""

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.document import EMBEDDING_DIMENSIONS, Document, DocumentChunk, DocumentStatus
from app.models.user import UserRole
from tests.integration.helpers import MakeUser
from tests.sql_support import DIM


def make_document(db_session: Session, subject_id: object) -> Document:
    document = Document(
        subject_id=subject_id,
        filename="notes.pdf",
        content_type="application/pdf",
        size_bytes=1234,
    )
    db_session.add(document)
    db_session.flush()
    return document


def make_subject_id(db_session: Session, make_user: MakeUser) -> object:
    from app.models.subject import Subject

    teacher = make_user("model-teacher@example.com", UserRole.TEACHER)
    subject = Subject(name="Algebra", teacher_id=teacher.id)
    db_session.add(subject)
    db_session.flush()
    return subject.id


def test_models_are_registered_and_the_dimension_constant_matches_the_schema() -> None:
    assert "documents" in Base.metadata.tables
    assert "document_chunks" in Base.metadata.tables
    assert EMBEDDING_DIMENSIONS == DIM == 384


def test_document_defaults_and_status_enum(db_session: Session, make_user: MakeUser) -> None:
    document = make_document(db_session, make_subject_id(db_session, make_user))
    db_session.refresh(document)

    assert document.status is DocumentStatus.PENDING
    assert document.chunks_count == 0
    assert document.error_message is None
    assert document.created_at is not None
    assert [member.value for member in DocumentStatus] == [
        "pending",
        "processing",
        "ready",
        "failed",
    ]


def test_chunk_round_trips_the_embedding_and_relates_to_its_document(
    db_session: Session, make_user: MakeUser
) -> None:
    subject_id = make_subject_id(db_session, make_user)
    document = make_document(db_session, subject_id)
    embedding = [0.0] * DIM
    embedding[7] = 2.0
    chunk = DocumentChunk(
        document_id=document.id,
        subject_id=subject_id,
        chunk_index=0,
        page_number=3,
        content="some course text",
        embedding=embedding,
    )
    db_session.add(chunk)
    db_session.flush()
    db_session.expire_all()

    loaded = db_session.execute(select(DocumentChunk)).scalar_one()
    assert len(loaded.embedding) == DIM
    assert loaded.embedding[7] == 2.0
    assert loaded.document.id == document.id
    assert [c.id for c in loaded.document.chunks] == [loaded.id]


def test_relationships_rely_on_database_cascades(db_session: Session, make_user: MakeUser) -> None:
    subject_id = make_subject_id(db_session, make_user)
    document = make_document(db_session, subject_id)
    db_session.add(
        DocumentChunk(
            document_id=document.id,
            subject_id=subject_id,
            chunk_index=0,
            content="text",
            embedding=[0.5] * DIM,
        )
    )
    db_session.flush()

    relationship = inspect(Document).relationships["chunks"]

    assert relationship.passive_deletes is True
    assert relationship.cascade.delete is False  # the database performs the cascade


def test_model_metadata_names_follow_the_project_convention() -> None:
    chunks = Base.metadata.tables["document_chunks"]
    documents = Base.metadata.tables["documents"]

    assert {c.name for c in chunks.constraints if c.name} >= {
        "pk_document_chunks",
        "uq_document_chunks_document_id",
        "fk_document_chunks_document_id_documents",
        "ck_document_chunks_embedding_norm_range",
    }
    assert {i.name for i in chunks.indexes} == {
        "ix_document_chunks_embedding",
        "ix_document_chunks_subject_id",
    }
    assert {i.name for i in documents.indexes} == {"ix_documents_subject_id"}
