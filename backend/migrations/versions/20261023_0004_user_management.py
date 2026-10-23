"""add administrative audit events and active curator guards

Revision ID: 20261023_0004
Revises: 20261023_0003
Create Date: 2026-10-23 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261023_0004"
down_revision: str | None = "20261023_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _validate_active_group_curators() -> None:
    invalid_group_id = op.get_bind().scalar(
        sa.text(
            """
            SELECT groups.id
            FROM groups
            JOIN users ON users.id = groups.curator_id
            WHERE users.role != 'admin' OR users.is_active != 1
            LIMIT 1
            """
        )
    )
    if invalid_group_id is not None:
        raise RuntimeError(
            f"Group {invalid_group_id} must be reassigned to an active admin before upgrade"
        )


def upgrade() -> None:
    _validate_active_group_curators()
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=False),
        sa.Column("target_user_id", sa.String(length=36), nullable=True),
        sa.Column("target_group_id", sa.String(length=36), nullable=True),
        sa.Column(
            "action",
            sa.Enum(
                "curator_created",
                "student_account_created",
                "password_reset",
                "user_deactivated",
                "curator_reassigned",
                "curator_offboarded",
                "owner_transferred",
                name="audit_action",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("details", sa.JSON(), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_audit_events_actor_user_id_users"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["users.id"],
            name=op.f("fk_audit_events_target_user_id_users"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_group_id"],
            ["groups.id"],
            name=op.f("fk_audit_events_target_group_id_groups"),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        "ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"], unique=False
    )
    op.create_index(
        "ix_audit_events_target_user_id", "audit_events", ["target_user_id"], unique=False
    )
    op.create_index(
        "ix_audit_events_target_group_id", "audit_events", ["target_group_id"], unique=False
    )
    op.create_index(
        "ix_audit_events_action_created_at",
        "audit_events",
        ["action", "created_at"],
        unique=False,
    )
    op.execute(
        """
        CREATE TRIGGER trg_groups_require_active_curator_insert
        BEFORE INSERT ON groups
        FOR EACH ROW
        WHEN NOT EXISTS (
            SELECT 1 FROM users
            WHERE id = NEW.curator_id
              AND role = 'admin'
              AND is_active = 1
        )
        BEGIN
            SELECT RAISE(ABORT, 'active_curator_required');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_groups_require_active_curator_update
        BEFORE UPDATE OF curator_id, curator_role ON groups
        FOR EACH ROW
        WHEN NOT EXISTS (
            SELECT 1 FROM users
            WHERE id = NEW.curator_id
              AND role = 'admin'
              AND is_active = 1
        )
        BEGIN
            SELECT RAISE(ABORT, 'active_curator_required');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_users_preserve_group_curator_update
        BEFORE UPDATE OF role, is_active ON users
        FOR EACH ROW
        WHEN OLD.role = 'admin'
          AND OLD.is_active = 1
          AND NOT (NEW.role = 'admin' AND NEW.is_active = 1)
          AND EXISTS (
              SELECT 1 FROM groups WHERE curator_id = OLD.id
          )
        BEGIN
            SELECT RAISE(ABORT, 'curator_has_groups');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_users_preserve_group_curator_update")
    op.execute("DROP TRIGGER IF EXISTS trg_groups_require_active_curator_update")
    op.execute("DROP TRIGGER IF EXISTS trg_groups_require_active_curator_insert")
    op.drop_index("ix_audit_events_action_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_target_group_id", table_name="audit_events")
    op.drop_index("ix_audit_events_target_user_id", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_user_id", table_name="audit_events")
    op.drop_table("audit_events")
