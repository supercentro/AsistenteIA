"""Create ingestion_jobs and add documents.error_code.

Hand-finished on purpose: Alembic does not compare CHECK constraints or partial-index predicates,
and the downgrade must leave 0004 exactly as it was (see the change reports).

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("error_code", sa.String(length=40), nullable=True))
    op.create_check_constraint(
        op.f("ck_documents_error_code_only_when_failed"),
        "documents",
        "error_code IS NULL OR status = 'failed'",
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_by", sa.String(length=64), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_jobs")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_ingestion_jobs_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("document_id", name=op.f("uq_ingestion_jobs_document_id")),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_ingestion_jobs_attempts_non_negative")),
        sa.CheckConstraint(
            "(locked_by IS NULL) = (locked_until IS NULL)",
            name=op.f("ck_ingestion_jobs_lease_consistent"),
        ),
    )
    op.create_index(
        "ix_ingestion_jobs_claimable",
        "ingestion_jobs",
        ["available_at"],
        postgresql_where=sa.text("payload IS NOT NULL"),
    )


def downgrade() -> None:
    # Dropping the table drops its indexes and constraints. In-flight jobs and their bytes are lost
    # by design; documents already `ready` and their chunks are kept. A failed document loses its
    # code but keeps its fixed message (`error_message`).
    op.drop_table("ingestion_jobs")
    op.drop_constraint(op.f("ck_documents_error_code_only_when_failed"), "documents", type_="check")
    op.drop_column("documents", "error_code")
