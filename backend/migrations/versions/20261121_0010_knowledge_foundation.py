"""add shared Knowledge documents and personal favorites

Revision ID: 20261121_0010
Revises: 20261028_0009
Create Date: 2026-11-21 23:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261121_0010"
down_revision: str | None = "20261028_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "kind",
            sa.Enum(
                "prompt",
                "chapter",
                name="knowledge_kind",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("html", sa.Text(), nullable=False),
        sa.Column("plain_text", sa.Text(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("updated_by_user_id", sa.String(36), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("version >= 1", name="version"),
        sa.CheckConstraint("position >= 0", name="position"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_knowledge_documents_created_by_users",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name="fk_knowledge_documents_updated_by_users",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )
    op.create_index(
        "ix_knowledge_documents_kind_archived",
        "knowledge_documents",
        ["kind", "archived_at"],
    )
    op.create_index("ix_knowledge_documents_category", "knowledge_documents", ["category"])
    op.create_index(
        "ix_knowledge_documents_updated_id",
        "knowledge_documents",
        ["updated_at", "id"],
    )
    op.create_table(
        "knowledge_favorites",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_knowledge_favorites_user_users",
            ondelete="CASCADE",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name="fk_knowledge_favorites_document_documents",
            ondelete="CASCADE",
            onupdate="RESTRICT",
        ),
    )
    op.create_index("ix_knowledge_favorites_document_id", "knowledge_favorites", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_favorites_document_id", table_name="knowledge_favorites")
    op.drop_table("knowledge_favorites")
    op.drop_index("ix_knowledge_documents_updated_id", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_category", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_kind_archived", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
