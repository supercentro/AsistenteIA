"""Give users.role a server default of 'student'.

Public registration no longer names the role: the application role has no INSERT privilege on
users.role (decision DD-9, option A of change `database-least-privilege`), so PostgreSQL supplies
`student`. Teacher accounts are created only by the administrative command, which sets the role
explicitly under its own database identity. Existing rows are not touched; the downgrade drops only
the default.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "role", server_default=sa.text("'student'"))


def downgrade() -> None:
    op.alter_column("users", "role", server_default=None)
