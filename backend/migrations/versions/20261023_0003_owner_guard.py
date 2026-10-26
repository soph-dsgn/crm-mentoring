"""protect the last active owner

Revision ID: 20261023_0003
Revises: 20261022_0002
Create Date: 2026-10-23 12:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261023_0003"
down_revision: str | None = "20261022_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return
    op.execute(
        """
        CREATE TRIGGER trg_users_preserve_active_owner_update
        BEFORE UPDATE OF role, is_owner, is_active ON users
        FOR EACH ROW
        WHEN OLD.role = 'admin'
          AND OLD.is_owner = 1
          AND OLD.is_active = 1
          AND NOT (NEW.role = 'admin' AND NEW.is_owner = 1 AND NEW.is_active = 1)
          AND NOT EXISTS (
              SELECT 1 FROM users
              WHERE id != OLD.id
                AND role = 'admin'
                AND is_owner = 1
                AND is_active = 1
          )
        BEGIN
            SELECT RAISE(ABORT, 'last_active_owner_required');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_users_preserve_active_owner_delete
        BEFORE DELETE ON users
        FOR EACH ROW
        WHEN OLD.role = 'admin'
          AND OLD.is_owner = 1
          AND OLD.is_active = 1
          AND NOT EXISTS (
              SELECT 1 FROM users
              WHERE id != OLD.id
                AND role = 'admin'
                AND is_owner = 1
                AND is_active = 1
          )
        BEGIN
            SELECT RAISE(ABORT, 'last_active_owner_required');
        END
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return
    op.execute("DROP TRIGGER IF EXISTS trg_users_preserve_active_owner_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_users_preserve_active_owner_update")
