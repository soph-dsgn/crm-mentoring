"""add strategies, sections, tasks, history and approvals

Revision ID: 20261025_0006
Revises: 20261025_0005
Create Date: 2026-10-25 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261025_0006"
down_revision: str | None = "20261025_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("source_metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["student_id"], ["students.id"], ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id"),
    )
    op.create_table(
        "strategy_sections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("strategy_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_id"], ["strategies.id"], ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        sa.CheckConstraint("position >= 0", name="non_negative_section_position"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "strategy_id", name="uq_strategy_sections_id_strategy"),
        sa.UniqueConstraint("strategy_id", "position", name="uq_strategy_sections_position"),
    )
    op.create_index(
        "ix_strategy_sections_strategy_id", "strategy_sections", ["strategy_id"], unique=False
    )
    op.create_table(
        "strategy_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("strategy_id", sa.String(length=36), nullable=False),
        sa.Column("section_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("materials", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("links", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("period_text", sa.String(length=255), server_default="", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "study_status",
            sa.Enum(
                "not_started",
                "in_progress",
                "hold",
                "done",
                name="study_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="not_started",
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["section_id", "strategy_id"],
            ["strategy_sections.id", "strategy_sections.strategy_id"],
            name="fk_strategy_tasks_section_strategy",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"], ["strategies.id"], ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        sa.CheckConstraint("position >= 0", name="non_negative_task_position"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("section_id", "position", name="uq_strategy_tasks_position"),
    )
    op.create_index("ix_strategy_tasks_section_id", "strategy_tasks", ["section_id"], unique=False)
    op.create_index("ix_strategy_tasks_strategy_id", "strategy_tasks", ["strategy_id"], unique=False)
    op.create_index(
        "ix_strategy_tasks_study_status", "strategy_tasks", ["study_status"], unique=False
    )
    op.create_table(
        "task_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("details", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["strategy_tasks.id"], ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_history_actor_user_id", "task_history", ["actor_user_id"], unique=False
    )
    op.create_index(
        "ix_task_history_task_created",
        "task_history",
        ["task_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "anya_approvals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "to_send",
                "sent",
                "reviewing",
                "revision",
                "approved",
                name="approval_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="to_send",
            nullable=False,
        ),
        sa.Column("comment", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["strategy_tasks.id"], ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index("ix_anya_approvals_status", "anya_approvals", ["status"], unique=False)
    op.execute(
        """
        CREATE TRIGGER trg_task_history_append_only_update
        BEFORE UPDATE ON task_history
        BEGIN
            SELECT RAISE(ABORT, 'task_history_append_only');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_task_history_append_only_delete
        BEFORE DELETE ON task_history
        BEGIN
            SELECT RAISE(ABORT, 'task_history_append_only');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_task_history_append_only_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_task_history_append_only_update")
    op.drop_index("ix_anya_approvals_status", table_name="anya_approvals")
    op.drop_table("anya_approvals")
    op.drop_index("ix_task_history_task_created", table_name="task_history")
    op.drop_index("ix_task_history_actor_user_id", table_name="task_history")
    op.drop_table("task_history")
    op.drop_index("ix_strategy_tasks_study_status", table_name="strategy_tasks")
    op.drop_index("ix_strategy_tasks_strategy_id", table_name="strategy_tasks")
    op.drop_index("ix_strategy_tasks_section_id", table_name="strategy_tasks")
    op.drop_table("strategy_tasks")
    op.drop_index("ix_strategy_sections_strategy_id", table_name="strategy_sections")
    op.drop_table("strategy_sections")
    op.drop_table("strategies")
