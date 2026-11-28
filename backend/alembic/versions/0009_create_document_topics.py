"""Create document_topic_sets and document_topics.

Change `frequent-questions-and-topics`. Two new tables of material metadata; no existing table
changes. Existing documents get no row: their topics are defined by the teacher, if wanted.
The privileges are not here: `db-migrate` applies the matrix of `app/db_privileges.py` afterwards.
`downgrade` drops both tables with their data.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_topic_sets",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("ranges_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "source IN ('bookmarks', 'teacher')",
            name=op.f("ck_document_topic_sets_source_known"),
        ),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_document_topic_sets_revision_positive")),
        sa.ForeignKeyConstraint(
            ["document_id", "subject_id"],
            ["documents.id", "documents.subject_id"],
            name=op.f("fk_document_topic_sets_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_id", name=op.f("pk_document_topic_sets")),
    )
    op.create_index(
        op.f("ix_document_topic_sets_subject_id"), "document_topic_sets", ["subject_id"]
    )
    op.create_table(
        "document_topics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("start_page", sa.Integer(), nullable=False),
        sa.Column("end_page", sa.Integer(), nullable=False),
        sa.CheckConstraint("position >= 0", name=op.f("ck_document_topics_position_non_negative")),
        sa.CheckConstraint(r"title ~ '\S'", name=op.f("ck_document_topics_title_not_blank")),
        sa.CheckConstraint(
            "start_page >= 1 AND end_page >= start_page",
            name=op.f("ck_document_topics_page_range"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document_topic_sets.document_id"],
            name=op.f("fk_document_topics_document_id_document_topic_sets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_topics")),
        sa.UniqueConstraint(
            "document_id", "position", name=op.f("uq_document_topics_document_id")
        ),
    )


def downgrade() -> None:
    op.drop_table("document_topics")
    op.drop_index(op.f("ix_document_topic_sets_subject_id"), table_name="document_topic_sets")
    op.drop_table("document_topic_sets")
