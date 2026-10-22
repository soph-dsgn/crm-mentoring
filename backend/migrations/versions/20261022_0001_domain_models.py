"""create users, groups, and students

Revision ID: 20261022_0001
Revises:
Create Date: 2026-10-22 20:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261022_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("login", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "admin",
                "student",
                name="user_role",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("is_owner", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "NOT is_owner OR role = 'admin'",
            name=op.f("ck_users_owner_requires_admin_role"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("id", "role", name="uq_users_id_role"),
        sa.UniqueConstraint("login", name=op.f("uq_users_login")),
    )
    op.create_table(
        "groups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("curator_id", sa.String(length=36), nullable=False),
        sa.Column(
            "curator_role",
            sa.Enum(
                "admin",
                "student",
                name="user_role",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="admin",
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("starts_at", sa.Date(), nullable=False),
        sa.Column("ends_at", sa.Date(), nullable=True),
        sa.Column("actual_ends_at", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "backlog",
                "active",
                "completed",
                "archived",
                name="group_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "status_before_archive",
            sa.Enum(
                "backlog",
                "active",
                "completed",
                "archived",
                name="previous_group_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("duration_months", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "curator_role = 'admin'",
            name=op.f("ck_groups_curator_requires_admin_role"),
        ),
        sa.CheckConstraint(
            "duration_months IS NULL OR duration_months > 0",
            name=op.f("ck_groups_positive_duration_months"),
        ),
        sa.CheckConstraint(
            "ends_at IS NULL OR starts_at <= ends_at",
            name=op.f("ck_groups_planned_dates_in_order"),
        ),
        sa.ForeignKeyConstraint(
            ["curator_id", "curator_role"],
            ["users.id", "users.role"],
            name="fk_groups_curator_users",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_groups")),
    )
    op.create_index("ix_groups_curator_id", "groups", ["curator_id"], unique=False)
    op.create_index("ix_groups_status", "groups", ["status"], unique=False)
    op.create_table(
        "students",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column(
            "user_role",
            sa.Enum(
                "admin",
                "student",
                name="user_role",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="student",
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("photo", sa.Text(), server_default="", nullable=False),
        sa.Column("avatar_index", sa.Integer(), server_default="-1", nullable=False),
        sa.Column(
            "stage",
            sa.Enum(
                "start",
                "portfolio",
                "search",
                name="student_stage",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="start",
            nullable=False,
        ),
        sa.Column("stage_known", sa.Boolean(), nullable=True),
        sa.Column("starts_at", sa.Date(), nullable=True),
        sa.Column("level", sa.String(length=255), server_default="", nullable=False),
        sa.Column("desired_position", sa.String(length=255), server_default="", nullable=False),
        sa.Column("career_goal", sa.Text(), server_default="", nullable=False),
        sa.Column("links", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("background", sa.Text(), server_default="", nullable=False),
        sa.Column("experience", sa.Text(), server_default="", nullable=False),
        sa.Column("strengths", sa.Text(), server_default="", nullable=False),
        sa.Column("growth_areas", sa.Text(), server_default="", nullable=False),
        sa.Column("difficulties", sa.Text(), server_default="", nullable=False),
        sa.Column("expectations", sa.Text(), server_default="", nullable=False),
        sa.Column("personal_notes", sa.Text(), server_default="", nullable=False),
        sa.Column("point_a", sa.Text(), server_default="", nullable=False),
        sa.Column("point_b", sa.Text(), server_default="", nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("strategy_updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "user_role = 'student'",
            name=op.f("ck_students_account_requires_student_role"),
        ),
        sa.CheckConstraint("age IS NULL OR age >= 0", name=op.f("ck_students_non_negative_age")),
        sa.CheckConstraint("avatar_index >= -1", name=op.f("ck_students_valid_avatar_index")),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
            name=op.f("fk_students_group_id_groups"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "user_role"],
            ["users.id", "users.role"],
            name="fk_students_user_users",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_students")),
        sa.UniqueConstraint("user_id", name=op.f("uq_students_user_id")),
    )
    op.create_index("ix_students_group_id", "students", ["group_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_students_group_id", table_name="students")
    op.drop_table("students")
    op.drop_index("ix_groups_status", table_name="groups")
    op.drop_index("ix_groups_curator_id", table_name="groups")
    op.drop_table("groups")
    op.drop_table("users")
