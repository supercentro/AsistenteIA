"""Create subjects and enrollments.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subjects")),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["users.id"],
            name=op.f("fk_subjects_teacher_id_users"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("teacher_id", "name", name=op.f("uq_subjects_teacher_id")),
    )
    op.create_table(
        "enrollments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollments")),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_enrollments_subject_id_subjects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["users.id"],
            name=op.f("fk_enrollments_student_id_users"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("subject_id", "student_id", name=op.f("uq_enrollments_subject_id")),
    )
    op.create_index(op.f("ix_enrollments_student_id"), "enrollments", ["student_id"])


def downgrade() -> None:
    op.drop_table("enrollments")
    op.drop_table("subjects")
