"""Add an optional display name to user accounts."""

import sqlalchemy as sa
from alembic import op

revision = "20261126_0013"
down_revision = "20261124_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Plain ADD COLUMN keeps the SQLite triggers that reference the users table intact.
    op.add_column(
        "users",
        sa.Column("display_name", sa.String(length=120), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "display_name")
