"""add meetings and homework review workflow

Revision ID: 20261026_0007
Revises: 20261025_0006
Create Date: 2026-10-26 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0007"
down_revision: str | None = "20261025_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("strategy_tasks") as batch_op:
        batch_op.add_column(
            sa.Column(
                "review_status",
                sa.Enum(
                    "none",
                    "pending",
                    "revision",
                    "accepted",
                    name="homework_review_status",
                    native_enum=False,
                    create_constraint=True,
                ),
                server_default="none",
                nullable=False,
            )
        )
        batch_op.create_index("ix_strategy_tasks_review_status", ["review_status"])

    op.create_table(
        "meetings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("student_id", sa.String(length=36), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["student_id"], ["students.id"], ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meetings_archived_at", "meetings", ["archived_at"], unique=False)
    op.create_index(
        "ix_meetings_student_date_id", "meetings", ["student_id", "date", "id"], unique=False
    )

    op.create_table(
        "homeworks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("strategy_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("links", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("submission_text", sa.Text(), server_default="", nullable=False),
        sa.Column("submission_links", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("curator_feedback", sa.Text(), server_default="", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "issued",
                "progress",
                "submitted",
                "revision",
                "accepted",
                name="homework_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_id"], ["strategies.id"], ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "strategy_id", name="uq_homeworks_id_strategy"),
    )
    op.create_index("ix_homeworks_archived_at", "homeworks", ["archived_at"], unique=False)
    op.create_index(
        "ix_homeworks_strategy_status", "homeworks", ["strategy_id", "status"], unique=False
    )

    op.create_table(
        "homework_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("homework_id", sa.String(length=36), nullable=False),
        sa.Column("strategy_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("materials", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("links", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("period_text", sa.String(length=255), server_default="", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["homework_id", "strategy_id"],
            ["homeworks.id", "homeworks.strategy_id"],
            name="fk_homework_items_homework_strategy",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["strategy_tasks.id"], ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("homework_id", "position", name="uq_homework_items_position"),
        sa.UniqueConstraint("homework_id", "task_id", name="uq_homework_items_task"),
    )
    op.create_index("ix_homework_items_task_id", "homework_items", ["task_id"], unique=False)

    op.create_table(
        "homework_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("homework_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "from_status",
            sa.Enum(
                "draft",
                "issued",
                "progress",
                "submitted",
                "revision",
                "accepted",
                name="homework_history_from_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            sa.Enum(
                "draft",
                "issued",
                "progress",
                "submitted",
                "revision",
                "accepted",
                name="homework_history_to_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("details", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["homework_id"], ["homeworks.id"], ondelete="RESTRICT", onupdate="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_homework_history_actor_user_id",
        "homework_history",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_homework_history_homework_created",
        "homework_history",
        ["homework_id", "created_at", "id"],
        unique=False,
    )

    op.execute(
        """
        CREATE TRIGGER trg_homework_items_strategy_insert
        BEFORE INSERT ON homework_items
        WHEN (SELECT strategy_id FROM strategy_tasks WHERE id = NEW.task_id) != NEW.strategy_id
        BEGIN
            SELECT RAISE(ABORT, 'homework_item_strategy_mismatch');
        END
        """
    )
    for table in ("homework_items", "homework_history"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_append_only_update
            BEFORE UPDATE ON {table}
            BEGIN
                SELECT RAISE(ABORT, '{table}_append_only');
            END
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_append_only_delete
            BEFORE DELETE ON {table}
            BEGIN
                SELECT RAISE(ABORT, '{table}_append_only');
            END
            """
        )


def downgrade() -> None:
    for table in ("homework_history", "homework_items"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only_delete")
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only_update")
    op.execute("DROP TRIGGER IF EXISTS trg_homework_items_strategy_insert")
    op.drop_index("ix_homework_history_homework_created", table_name="homework_history")
    op.drop_index("ix_homework_history_actor_user_id", table_name="homework_history")
    op.drop_table("homework_history")
    op.drop_index("ix_homework_items_task_id", table_name="homework_items")
    op.drop_table("homework_items")
    op.drop_index("ix_homeworks_strategy_status", table_name="homeworks")
    op.drop_index("ix_homeworks_archived_at", table_name="homeworks")
    op.drop_table("homeworks")
    op.drop_index("ix_meetings_student_date_id", table_name="meetings")
    op.drop_index("ix_meetings_archived_at", table_name="meetings")
    op.drop_table("meetings")
    with op.batch_alter_table("strategy_tasks") as batch_op:
        batch_op.drop_index("ix_strategy_tasks_review_status")
        batch_op.drop_constraint(
            op.f("ck_strategy_tasks_homework_review_status"), type_="check"
        )
        batch_op.drop_column("review_status")
