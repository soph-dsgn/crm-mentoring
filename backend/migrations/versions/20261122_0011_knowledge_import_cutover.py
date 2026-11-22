"""add Knowledge import runs, mappings, and server cutover state

Revision ID: 20261122_0011
Revises: 20261121_0010
Create Date: 2026-11-22 19:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0011"
down_revision: str | None = "20261121_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_library_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "active",
                name="knowledge_library_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("activated_by_user_id", sa.String(36)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("id = 1", name="singleton"),
        sa.CheckConstraint("version >= 1", name="version"),
        sa.ForeignKeyConstraint(
            ["activated_by_user_id"],
            ["users.id"],
            name="fk_knowledge_library_state_activated_by_users",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )
    op.bulk_insert(
        sa.table(
            "knowledge_library_state",
            sa.column("id", sa.Integer()),
            sa.column("status", sa.String()),
            sa.column("version", sa.Integer()),
        ),
        [{"id": 1, "status": "pending", "version": 1}],
    )
    op.create_table(
        "knowledge_import_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("request_checksum", sa.String(64), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column(
            "source_format",
            sa.Enum(
                "knowledge_data_v1",
                "parsed_documents",
                name="knowledge_source_format",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "mode",
            sa.Enum(
                "initial",
                "additional",
                name="knowledge_import_mode",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.String(36), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("checksum", name="uq_knowledge_import_runs_checksum"),
        sa.UniqueConstraint("request_checksum", name="uq_knowledge_import_runs_request_checksum"),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_knowledge_import_runs_actor_users",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )
    op.create_index("ix_knowledge_import_runs_created_at", "knowledge_import_runs", ["created_at"])
    op.create_table(
        "knowledge_import_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("import_run_id", sa.String(36), nullable=False),
        sa.Column("source_key", sa.String(768), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("length(source_key) > 0", name="source_key_not_empty"),
        sa.UniqueConstraint(
            "import_run_id", "source_key", name="uq_knowledge_import_mapping_source"
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id"],
            ["knowledge_import_runs.id"],
            name="fk_knowledge_import_mappings_run_runs",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["knowledge_documents.id"],
            name="fk_knowledge_import_mappings_target_documents",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )
    op.create_index(
        "ix_knowledge_import_mappings_source_key", "knowledge_import_mappings", ["source_key"]
    )
    op.create_index(
        "ix_knowledge_import_mappings_target_id", "knowledge_import_mappings", ["target_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_import_mappings_target_id", table_name="knowledge_import_mappings")
    op.drop_index("ix_knowledge_import_mappings_source_key", table_name="knowledge_import_mappings")
    op.drop_table("knowledge_import_mappings")
    op.drop_index("ix_knowledge_import_runs_created_at", table_name="knowledge_import_runs")
    op.drop_table("knowledge_import_runs")
    op.drop_table("knowledge_library_state")
