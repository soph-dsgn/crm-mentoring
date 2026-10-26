"""add PostgreSQL integrity triggers

Revision ID: 20261026_0008
Revises: 20261026_0007
Create Date: 2026-10-26 18:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261026_0008"
down_revision: str | None = "20261026_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE FUNCTION kuratorskaya_guard_active_owner() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM pg_advisory_xact_lock(7217318685417055441);
            IF TG_OP = 'DELETE' THEN
                IF OLD.role = 'admin' AND OLD.is_owner AND OLD.is_active
                   AND NOT EXISTS (
                       SELECT 1 FROM users
                       WHERE id != OLD.id AND role = 'admin' AND is_owner AND is_active
                   ) THEN
                    RAISE EXCEPTION 'last_active_owner_required' USING ERRCODE = '23514';
                END IF;
                RETURN OLD;
            END IF;
            IF OLD.role = 'admin' AND OLD.is_owner AND OLD.is_active
               AND NOT (NEW.role = 'admin' AND NEW.is_owner AND NEW.is_active)
               AND NOT EXISTS (
                   SELECT 1 FROM users
                   WHERE id != OLD.id AND role = 'admin' AND is_owner AND is_active
               ) THEN
                RAISE EXCEPTION 'last_active_owner_required' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_users_preserve_active_owner_update
        BEFORE UPDATE OF role, is_owner, is_active ON users
        FOR EACH ROW EXECUTE FUNCTION kuratorskaya_guard_active_owner()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_users_preserve_active_owner_delete
        BEFORE DELETE ON users
        FOR EACH ROW EXECUTE FUNCTION kuratorskaya_guard_active_owner()
        """
    )

    op.execute(
        """
        CREATE FUNCTION kuratorskaya_require_active_curator() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM 1 FROM users
            WHERE id = NEW.curator_id AND role = 'admin' AND is_active
            FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'active_curator_required' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_groups_require_active_curator_insert
        BEFORE INSERT ON groups
        FOR EACH ROW EXECUTE FUNCTION kuratorskaya_require_active_curator()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_groups_require_active_curator_update
        BEFORE UPDATE OF curator_id, curator_role ON groups
        FOR EACH ROW EXECUTE FUNCTION kuratorskaya_require_active_curator()
        """
    )

    op.execute(
        """
        CREATE FUNCTION kuratorskaya_preserve_group_curator() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.role = 'admin' AND OLD.is_active
               AND NOT (NEW.role = 'admin' AND NEW.is_active)
               AND EXISTS (SELECT 1 FROM groups WHERE curator_id = OLD.id) THEN
                RAISE EXCEPTION 'curator_has_groups' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_users_preserve_group_curator_update
        BEFORE UPDATE OF role, is_active ON users
        FOR EACH ROW EXECUTE FUNCTION kuratorskaya_preserve_group_curator()
        """
    )

    op.execute(
        """
        CREATE FUNCTION kuratorskaya_reject_archived_group_student() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE group_status varchar;
        BEGIN
            SELECT status INTO group_status FROM groups WHERE id = NEW.group_id FOR UPDATE;
            IF group_status = 'archived' THEN
                RAISE EXCEPTION 'group_archived' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_students_reject_archived_group_insert
        BEFORE INSERT ON students
        FOR EACH ROW EXECUTE FUNCTION kuratorskaya_reject_archived_group_student()
        """
    )

    op.execute(
        """
        CREATE FUNCTION kuratorskaya_reject_homework_item_mismatch() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM strategy_tasks
                WHERE id = NEW.task_id AND strategy_id = NEW.strategy_id
            ) THEN
                RAISE EXCEPTION 'homework_item_strategy_mismatch' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_homework_items_strategy_insert
        BEFORE INSERT ON homework_items
        FOR EACH ROW EXECUTE FUNCTION kuratorskaya_reject_homework_item_mismatch()
        """
    )

    op.execute(
        """
        CREATE FUNCTION kuratorskaya_reject_immutable_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '%_append_only', TG_TABLE_NAME USING ERRCODE = '23514';
        END
        $$
        """
    )
    for table in ("task_history", "homework_items", "homework_history"):
        for operation in ("update", "delete"):
            op.execute(
                f"""
                CREATE TRIGGER trg_{table}_append_only_{operation}
                BEFORE {operation.upper()} ON {table}
                FOR EACH ROW EXECUTE FUNCTION kuratorskaya_reject_immutable_change()
                """
            )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table in ("homework_history", "homework_items", "task_history"):
        for operation in ("delete", "update"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only_{operation} ON {table}")
    op.execute("DROP FUNCTION IF EXISTS kuratorskaya_reject_immutable_change()")
    op.execute("DROP TRIGGER IF EXISTS trg_homework_items_strategy_insert ON homework_items")
    op.execute("DROP FUNCTION IF EXISTS kuratorskaya_reject_homework_item_mismatch()")
    op.execute("DROP TRIGGER IF EXISTS trg_students_reject_archived_group_insert ON students")
    op.execute("DROP FUNCTION IF EXISTS kuratorskaya_reject_archived_group_student()")
    op.execute("DROP TRIGGER IF EXISTS trg_users_preserve_group_curator_update ON users")
    op.execute("DROP FUNCTION IF EXISTS kuratorskaya_preserve_group_curator()")
    op.execute("DROP TRIGGER IF EXISTS trg_groups_require_active_curator_update ON groups")
    op.execute("DROP TRIGGER IF EXISTS trg_groups_require_active_curator_insert ON groups")
    op.execute("DROP FUNCTION IF EXISTS kuratorskaya_require_active_curator()")
    op.execute("DROP TRIGGER IF EXISTS trg_users_preserve_active_owner_delete ON users")
    op.execute("DROP TRIGGER IF EXISTS trg_users_preserve_active_owner_update ON users")
    op.execute("DROP FUNCTION IF EXISTS kuratorskaya_guard_active_owner()")
