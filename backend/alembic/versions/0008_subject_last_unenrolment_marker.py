"""Add subjects.last_unenrolment_at, the marker of the last unenrolment.

Change `activity-privacy-hardening` (A2). One nullable timestamp on the subject, with no reference
to a student. The aggregate teacher activity never shows a week that starts before it, so a read
made after a removal cannot be subtracted from a read made before it. The route that removes an
enrolment sets it in the same transaction.

Backfill: a subject that already holds conversations gets the time of this migration (a removal
made before the marker existed left no trace, and earlier reading of its history cannot be ruled
out, so its history stays withheld); a subject without conversations has no history and stays null.
The `EXISTS` over `conversations` is one semi-join scan, acceptable for the expected sizes; adding the column is a catalog change only.
The privileges are not here: `db-migrate` applies the matrix of `app/db_privileges.py` afterwards.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "subjects", sa.Column("last_unenrolment_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "UPDATE subjects SET last_unenrolment_at = clock_timestamp() "
        "WHERE EXISTS (SELECT 1 FROM conversations WHERE conversations.subject_id = subjects.id)"
    )


def downgrade() -> None:
    op.drop_column("subjects", "last_unenrolment_at")
