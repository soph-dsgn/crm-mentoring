"""add optimistic versions and extensible business audit actions

Revision ID: 20261025_0005
Revises: 20261023_0004
Create Date: 2026-10-25 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261025_0005"
down_revision: str | None = "20261023_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_AUDIT_ACTIONS = (
    "curator_created",
    "student_account_created",
    "password_reset",
    "user_deactivated",
    "curator_reassigned",
    "curator_offboarded",
    "owner_transferred",
)


def _drop_curator_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_users_preserve_group_curator_update")
    op.execute("DROP TRIGGER IF EXISTS trg_groups_require_active_curator_update")
    op.execute("DROP TRIGGER IF EXISTS trg_groups_require_active_curator_insert")


def _create_curator_triggers() -> None:
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


def _validate_audit_actions_for_downgrade() -> None:
    placeholders = ", ".join(f":action_{index}" for index, _ in enumerate(OLD_AUDIT_ACTIONS))
    unsupported = op.get_bind().scalar(
        sa.text(
            f"SELECT action FROM audit_events WHERE action NOT IN ({placeholders}) LIMIT 1"
        ),
        {f"action_{index}": action for index, action in enumerate(OLD_AUDIT_ACTIONS)},
    )
    if unsupported is not None:
        raise RuntimeError(
            f"Downgrade cannot represent audit action {unsupported}; "
            "preserve or remove newer business audit events explicitly"
        )


def upgrade() -> None:
    op.add_column(
        "groups",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "students",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    old_type = sa.Enum(
        *OLD_AUDIT_ACTIONS,
        name="audit_action",
        native_enum=False,
        create_constraint=True,
    )
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.alter_column(
            "action",
            existing_type=old_type,
            type_=sa.String(length=64),
            existing_nullable=False,
        )
    if op.get_bind().dialect.name != "sqlite":
        return
    op.execute(
        """
        CREATE TRIGGER trg_students_reject_archived_group_insert
        BEFORE INSERT ON students
        FOR EACH ROW
        WHEN EXISTS (
            SELECT 1 FROM groups
            WHERE id = NEW.group_id AND status = 'archived'
        )
        BEGIN
            SELECT RAISE(ABORT, 'group_archived');
        END
        """
    )


def downgrade() -> None:
    _validate_audit_actions_for_downgrade()
    is_sqlite = op.get_bind().dialect.name == "sqlite"
    if is_sqlite:
        op.execute("DROP TRIGGER IF EXISTS trg_students_reject_archived_group_insert")
    old_type = sa.Enum(
        *OLD_AUDIT_ACTIONS,
        name="audit_action",
        native_enum=False,
        create_constraint=True,
    )
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.alter_column(
            "action",
            existing_type=sa.String(length=64),
            type_=old_type,
            existing_nullable=False,
        )
    with op.batch_alter_table("students") as batch_op:
        batch_op.drop_column("version")
    # SQLite batch mode rebuilds the table. Drop triggers that reference
    # ``groups`` before the temporary table swap, then restore the exact
    # guards owned by revision 0004 for the downgraded schema.
    if is_sqlite:
        _drop_curator_triggers()
    with op.batch_alter_table("groups") as batch_op:
        batch_op.drop_column("version")
    if is_sqlite:
        _create_curator_triggers()
