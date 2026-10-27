"""add legacy import tracking

Revision ID: 20261028_0009
Revises: 20261026_0008
Create Date: 2026-10-28 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261028_0009"
down_revision: str | None = "20261026_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("checksum", sa.String(64), nullable=False, unique=True),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT", onupdate="RESTRICT"),
    )
    op.create_index("ix_import_runs_created_at", "import_runs", ["created_at"])
    op.create_table(
        "legacy_id_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("import_run_id", sa.String(36), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("legacy_id", sa.String(255), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(["import_run_id"], ["import_runs.id"], ondelete="RESTRICT", onupdate="RESTRICT"),
        sa.UniqueConstraint("import_run_id", "entity_type", "legacy_id", name="uq_legacy_mapping"),
    )
    op.create_index("ix_legacy_mapping_target", "legacy_id_mappings", ["entity_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_legacy_mapping_target", table_name="legacy_id_mappings")
    op.drop_table("legacy_id_mappings")
    op.drop_index("ix_import_runs_created_at", table_name="import_runs")
    op.drop_table("import_runs")
