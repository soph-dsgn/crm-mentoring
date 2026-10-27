from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.session import build_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config(database_url: str) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["database_url"] = database_url
    return config


def test_initial_migration_upgrade_and_downgrade_clean_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    config = alembic_config(database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == {
            "alembic_version",
            "anya_approvals",
            "audit_events",
            "auth_sessions",
            "groups",
            "homework_history",
            "homework_items",
            "homeworks",
            "import_runs",
            "legacy_id_mappings",
            "login_attempts",
            "meetings",
            "strategies",
            "strategy_sections",
            "strategy_tasks",
            "students",
            "task_history",
            "users",
        }
        assert {column["name"] for column in inspector.get_columns("import_runs")} >= {
            "checksum",
            "source_version",
            "actor_user_id",
            "counts",
        }
        assert {column["name"] for column in inspector.get_columns("users")} >= {"normalized_login"}
        assert {column["name"] for column in inspector.get_columns("groups")} >= {
            "id",
            "curator_id",
            "name",
            "status",
            "version",
        }
        assert {column["name"] for column in inspector.get_columns("students")} >= {
            "id",
            "group_id",
            "user_id",
            "name",
            "version",
        }
        assert {column["name"] for column in inspector.get_columns("strategy_tasks")} >= {
            "review_status"
        }
        assert {index["name"] for index in inspector.get_indexes("groups")} >= {
            "ix_groups_curator_id",
            "ix_groups_status",
        }
        assert {index["name"] for index in inspector.get_indexes("audit_events")} >= {
            "ix_audit_events_action_created_at",
            "ix_audit_events_actor_user_id",
            "ix_audit_events_target_group_id",
            "ix_audit_events_target_user_id",
        }
        audit_foreign_keys = {
            constraint["name"]: constraint
            for constraint in inspector.get_foreign_keys("audit_events")
        }
        assert audit_foreign_keys["fk_audit_events_actor_user_id_users"]["options"] == {
            "ondelete": "RESTRICT",
            "onupdate": "RESTRICT",
        }
        assert audit_foreign_keys["fk_audit_events_target_user_id_users"]["options"] == {
            "ondelete": "RESTRICT",
            "onupdate": "RESTRICT",
        }
        assert audit_foreign_keys["fk_audit_events_target_group_id_groups"]["options"] == {
            "ondelete": "RESTRICT",
            "onupdate": "RESTRICT",
        }
        user_unique_constraints = {
            (constraint["name"], tuple(constraint["column_names"]))
            for constraint in inspector.get_unique_constraints("users")
        }
        assert ("uq_users_login", ("login",)) in user_unique_constraints
        assert ("uq_users_id_role", ("id", "role")) in user_unique_constraints
        assert {
            (constraint["name"], tuple(constraint["column_names"]))
            for constraint in inspector.get_unique_constraints("students")
        } >= {("uq_students_user_id", ("user_id",))}

        group_curator_fk = next(
            constraint
            for constraint in inspector.get_foreign_keys("groups")
            if constraint["name"] == "fk_groups_curator_users"
        )
        assert group_curator_fk["constrained_columns"] == ["curator_id", "curator_role"]
        assert group_curator_fk["referred_columns"] == ["id", "role"]
        assert group_curator_fk["options"] == {"ondelete": "RESTRICT", "onupdate": "RESTRICT"}

        student_user_fk = next(
            constraint
            for constraint in inspector.get_foreign_keys("students")
            if constraint["name"] == "fk_students_user_users"
        )
        assert student_user_fk["constrained_columns"] == ["user_id", "user_role"]
        assert student_user_fk["referred_columns"] == ["id", "role"]
        assert student_user_fk["options"] == {"ondelete": "RESTRICT", "onupdate": "RESTRICT"}
    finally:
        engine.dispose()

    command.downgrade(config, "base")

    downgraded_engine = create_engine(database_url)
    try:
        assert inspect(downgraded_engine).get_table_names() == ["alembic_version"]
    finally:
        downgraded_engine.dispose()


def test_auth_migration_preserves_users_and_downgrades_to_domain_revision(tmp_path: Path) -> None:
    database_path = tmp_path / "auth-migration.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    config = alembic_config(database_url)
    command.upgrade(config, "20261022_0001")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, login, role, password_hash,
                        must_change_password, is_active, is_owner
                    ) VALUES (
                        'existing-user', '  Existing.User  ', 'admin', 'existing-hash',
                        1, 1, 0
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO groups (
                        id, curator_id, curator_role, name, starts_at, status
                    ) VALUES (
                        'existing-group', 'existing-user', 'admin',
                        'Existing group', '2026-10-01', 'active'
                    )
                    """
                )
            )
    finally:
        engine.dispose()

    command.upgrade(config, "head")

    upgraded_engine = create_engine(database_url)
    try:
        inspector = inspect(upgraded_engine)
        assert {"auth_sessions", "login_attempts"} <= set(inspector.get_table_names())
        unique_constraints = {
            (item["name"], tuple(item["column_names"]))
            for item in inspector.get_unique_constraints("users")
        }
        assert ("uq_users_normalized_login", ("normalized_login",)) in unique_constraints
        auth_session_unique_constraints = {
            (item["name"], tuple(item["column_names"]))
            for item in inspector.get_unique_constraints("auth_sessions")
        }
        assert ("uq_auth_sessions_token_hash", ("token_hash",)) in (auth_session_unique_constraints)
        assert {item["name"] for item in inspector.get_indexes("auth_sessions")} >= {
            "ix_auth_sessions_user_id"
        }
        assert {item["name"] for item in inspector.get_indexes("login_attempts")} >= {
            "ix_login_attempts_client_time",
            "ix_login_attempts_login_time",
        }
        session_user_fk = next(
            item
            for item in inspector.get_foreign_keys("auth_sessions")
            if item["name"] == "fk_auth_sessions_user_id_users"
        )
        assert session_user_fk["constrained_columns"] == ["user_id"]
        assert session_user_fk["referred_columns"] == ["id"]
        assert session_user_fk["options"] == {"ondelete": "CASCADE", "onupdate": "RESTRICT"}
        with upgraded_engine.connect() as connection:
            row = connection.execute(
                text("SELECT login, normalized_login, password_hash FROM users")
            ).one()
            assert row == ("  Existing.User  ", "existing.user", "existing-hash")
            assert connection.scalar(text("SELECT name FROM groups")) == "Existing group"
    finally:
        upgraded_engine.dispose()

    command.downgrade(config, "20261022_0001")

    downgraded_engine = create_engine(database_url)
    try:
        inspector = inspect(downgraded_engine)
        assert "auth_sessions" not in inspector.get_table_names()
        assert "login_attempts" not in inspector.get_table_names()
        assert "normalized_login" not in {
            column["name"] for column in inspector.get_columns("users")
        }
        with downgraded_engine.connect() as connection:
            assert connection.scalar(text("SELECT login FROM users")) == "  Existing.User  "
    finally:
        downgraded_engine.dispose()


def test_auth_migration_login_conflict_leaves_domain_schema_unchanged(tmp_path: Path) -> None:
    database_path = tmp_path / "auth-migration-conflict.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    config = alembic_config(database_url)
    command.upgrade(config, "20261022_0001")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            for user_id, login in (("first", "CaseUser"), ("second", "caseuser")):
                connection.execute(
                    text(
                        """
                        INSERT INTO users (id, login, role, password_hash)
                        VALUES (:user_id, :login, 'admin', 'existing-hash')
                        """
                    ),
                    {"user_id": user_id, "login": login},
                )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="duplicate logins"):
        command.upgrade(config, "head")

    inspected_engine = create_engine(database_url)
    try:
        inspector = inspect(inspected_engine)
        assert "normalized_login" not in {
            column["name"] for column in inspector.get_columns("users")
        }
        assert "auth_sessions" not in inspector.get_table_names()
        with inspected_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "20261022_0001"
            )
    finally:
        inspected_engine.dispose()


def test_strategies_migration_preserves_domain_data_and_enforces_history(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "strategies-migration.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    config = alembic_config(database_url)
    command.upgrade(config, "20261025_0005")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, login, normalized_login, role, password_hash,
                        must_change_password, is_active, is_owner
                    ) VALUES ('owner', 'owner', 'owner', 'admin', 'hash', 0, 1, 1)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO groups (
                        id, curator_id, curator_role, name, starts_at, status
                    ) VALUES ('group', 'owner', 'admin', 'Group', '2026-01-01', 'active')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO students (id, group_id, name, user_role, stage)
                    VALUES ('student', 'group', 'Student', 'student', 'start')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO students (id, group_id, name, user_role, stage)
                    VALUES ('student-2', 'group', 'Student 2', 'student', 'start')
                    """
                )
            )
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    upgraded = build_engine(database_url)
    try:
        with upgraded.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO strategies (id, student_id) VALUES ('strategy', 'student');
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO strategy_sections (id, strategy_id, title, position)
                    VALUES ('section', 'strategy', 'Section', 0)
                    """
                )
            )
            connection.execute(
                text("INSERT INTO strategies (id, student_id) VALUES ('strategy-2', 'student-2')")
            )
            connection.execute(
                text(
                    """
                    INSERT INTO strategy_sections (id, strategy_id, title, position)
                    VALUES ('section-2', 'strategy-2', 'Section 2', 0)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO strategy_tasks (
                        id, strategy_id, section_id, title, position
                    ) VALUES ('task', 'strategy', 'section', 'Task', 0)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO task_history (id, task_id, actor_user_id, event_type)
                    VALUES ('history', 'task', 'owner', 'task_created')
                    """
                )
            )
        assert inspect(upgraded).get_unique_constraints("strategies")
        with (
            pytest.raises(IntegrityError, match="task_history_append_only"),
            upgraded.begin() as connection,
        ):
            connection.execute(
                text("UPDATE task_history SET event_type = 'changed' WHERE id = 'history'")
            )
        with (
            pytest.raises(IntegrityError, match="non_negative_task_position"),
            upgraded.begin() as connection,
        ):
            connection.execute(text("UPDATE strategy_tasks SET position = -1 WHERE id = 'task'"))
        with (
            pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"),
            upgraded.begin() as connection,
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO strategy_tasks (
                        id, strategy_id, section_id, title, position
                    ) VALUES ('cross-task', 'strategy', 'section-2', 'Cross', 1)
                    """
                )
            )
        with (
            pytest.raises(IntegrityError, match="task_history_append_only"),
            upgraded.begin() as connection,
        ):
            connection.execute(text("DELETE FROM task_history WHERE id = 'history'"))
        with upgraded.connect() as connection:
            assert connection.scalar(text("SELECT name FROM students WHERE id = 'student'")) == (
                "Student"
            )
            assert connection.scalar(text("SELECT event_type FROM task_history")) == "task_created"
    finally:
        upgraded.dispose()

    command.downgrade(config, "20261025_0005")
    downgraded = create_engine(database_url)
    try:
        tables = inspect(downgraded).get_table_names()
        assert "strategies" not in tables
        with downgraded.connect() as connection:
            assert connection.scalar(text("SELECT name FROM students WHERE id = 'student'")) == (
                "Student"
            )
    finally:
        downgraded.dispose()


def test_meetings_homeworks_migration_preserves_tasks_and_enforces_snapshots(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "meetings-homeworks-migration.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    config = alembic_config(database_url)
    command.upgrade(config, "20261025_0006")
    engine = build_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, login, normalized_login, role, password_hash,
                        must_change_password, is_active, is_owner
                    ) VALUES ('owner', 'owner', 'owner', 'admin', 'hash', 0, 1, 1)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO groups (id, curator_id, curator_role, name, starts_at, status)
                    VALUES ('group', 'owner', 'admin', 'Group', '2026-01-01', 'active')
                    """
                )
            )
            for suffix in ("one", "two"):
                connection.execute(
                    text(
                        """
                        INSERT INTO students (id, group_id, name, user_role, stage)
                        VALUES (:student_id, 'group', :name, 'student', 'start')
                        """
                    ),
                    {"student_id": f"student-{suffix}", "name": suffix},
                )
                connection.execute(
                    text(
                        "INSERT INTO strategies (id, student_id) VALUES (:strategy_id, :student_id)"
                    ),
                    {"strategy_id": f"strategy-{suffix}", "student_id": f"student-{suffix}"},
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO strategy_sections (id, strategy_id, title, position)
                        VALUES (:section_id, :strategy_id, 'Section', 0)
                        """
                    ),
                    {"section_id": f"section-{suffix}", "strategy_id": f"strategy-{suffix}"},
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO strategy_tasks (id, strategy_id, section_id, title, position)
                        VALUES (:task_id, :strategy_id, :section_id, 'Task', 0)
                        """
                    ),
                    {
                        "task_id": f"task-{suffix}",
                        "strategy_id": f"strategy-{suffix}",
                        "section_id": f"section-{suffix}",
                    },
                )
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    upgraded = build_engine(database_url)
    try:
        with upgraded.begin() as connection:
            assert (
                connection.scalar(
                    text("SELECT review_status FROM strategy_tasks WHERE id = 'task-one'")
                )
                == "none"
            )
            connection.execute(
                text(
                    """
                    INSERT INTO meetings (id, student_id, date, title)
                    VALUES ('meeting', 'student-one', '2026-10-26', 'Meeting')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO homeworks (id, strategy_id, title)
                    VALUES ('homework', 'strategy-one', 'Homework')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO homework_items (
                        id, homework_id, strategy_id, task_id, position, title
                    ) VALUES (
                        'item', 'homework', 'strategy-one', 'task-one', 0, 'Snapshot'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO homework_history (
                        id, homework_id, actor_user_id, event_type, from_status, to_status
                    ) VALUES (
                        'history', 'homework', 'owner', 'homework_status_changed',
                        'draft', 'issued'
                    )
                    """
                )
            )
        with (
            pytest.raises(IntegrityError, match="homework_item_strategy_mismatch"),
            upgraded.begin() as connection,
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO homework_items (
                        id, homework_id, strategy_id, task_id, position, title
                    ) VALUES (
                        'cross-item', 'homework', 'strategy-one', 'task-two', 1, 'Cross'
                    )
                    """
                )
            )
        for statement, marker in (
            (
                "UPDATE homework_items SET title = 'Changed' WHERE id = 'item'",
                "homework_items_append_only",
            ),
            ("DELETE FROM homework_history WHERE id = 'history'", "homework_history_append_only"),
        ):
            with pytest.raises(IntegrityError, match=marker), upgraded.begin() as connection:
                connection.execute(text(statement))
    finally:
        upgraded.dispose()

    command.downgrade(config, "20261025_0006")
    downgraded = build_engine(database_url)
    try:
        inspector = inspect(downgraded)
        assert {"meetings", "homeworks", "homework_items", "homework_history"}.isdisjoint(
            inspector.get_table_names()
        )
        assert "review_status" not in {
            column["name"] for column in inspector.get_columns("strategy_tasks")
        }
        with downgraded.connect() as connection:
            assert connection.scalar(
                text("SELECT title FROM strategy_tasks WHERE id = 'task-one'")
            ) == ("Task")
    finally:
        downgraded.dispose()


def test_owner_guard_migration_preserves_one_owner_under_concurrent_updates(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "owner-guard.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    config = alembic_config(database_url)
    command.upgrade(config, "head")
    engine = create_engine(database_url, connect_args={"timeout": 5})
    try:
        with engine.begin() as connection:
            for user_id in ("owner-one", "owner-two"):
                connection.execute(
                    text(
                        """
                        INSERT INTO users (
                            id, login, normalized_login, role, password_hash,
                            must_change_password, is_active, is_owner
                        ) VALUES (
                            :user_id, :user_id, :user_id, 'admin', 'hash', 0, 1, 1
                        )
                        """
                    ),
                    {"user_id": user_id},
                )

        barrier = Barrier(2)

        def deactivate(user_id: str) -> bool:
            try:
                with engine.begin() as connection:
                    barrier.wait()
                    connection.execute(
                        text("UPDATE users SET is_active = 0 WHERE id = :user_id"),
                        {"user_id": user_id},
                    )
                return True
            except IntegrityError:
                return False

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(deactivate, ("owner-one", "owner-two")))

        with engine.connect() as connection:
            active_owners = connection.scalar(
                text(
                    """
                    SELECT count(*) FROM users
                    WHERE role = 'admin' AND is_owner = 1 AND is_active = 1
                    """
                )
            )
            trigger_names = set(
                connection.scalars(
                    text(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type = 'trigger' AND tbl_name = 'users'
                        """
                    )
                )
            )
        assert outcomes.count(True) == 1
        assert active_owners == 1
        assert trigger_names >= {
            "trg_users_preserve_active_owner_update",
            "trg_users_preserve_active_owner_delete",
        }
    finally:
        engine.dispose()

    command.downgrade(config, "20261022_0002")
    downgraded_engine = create_engine(database_url)
    try:
        with downgraded_engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        """
                    SELECT count(*) FROM sqlite_master
                    WHERE type = 'trigger' AND tbl_name = 'users'
                    """
                    )
                )
                == 0
            )
    finally:
        downgraded_engine.dispose()


def test_user_management_migration_preserves_domain_data_and_downgrades_cleanly(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "user-management-migration.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    config = alembic_config(database_url)
    command.upgrade(config, "20261023_0003")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, login, normalized_login, role, password_hash,
                        must_change_password, is_active, is_owner
                    ) VALUES ('owner', 'owner', 'owner', 'admin', 'hash', 0, 1, 1)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO groups (
                        id, curator_id, curator_role, name, starts_at,
                        status, status_before_archive
                    ) VALUES (
                        'group', 'owner', 'admin', 'Group', '2026-01-01',
                        'archived', 'active'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO students (id, group_id, name, user_role, stage)
                    VALUES ('student', 'group', 'Student', 'student', 'start')
                    """
                )
            )
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    upgraded_engine = create_engine(database_url)
    try:
        with upgraded_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events (
                        id, actor_user_id, target_group_id, action, details
                    ) VALUES (
                        'event', 'owner', 'group', 'curator_reassigned',
                        '{"source":"migration-test"}'
                    )
                    """
                )
            )
            assert connection.scalar(text("SELECT name FROM groups WHERE id = 'group'")) == "Group"
            assert (
                connection.scalar(text("SELECT name FROM students WHERE id = 'student'"))
                == "Student"
            )
            assert connection.scalar(text("SELECT count(*) FROM audit_events")) == 1
            assert connection.scalar(text("SELECT version FROM groups WHERE id = 'group'")) == 1
            assert connection.scalar(text("SELECT version FROM students WHERE id = 'student'")) == 1
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events (
                        id, actor_user_id, target_group_id, action, details
                    ) VALUES (
                        'business-event', 'owner', 'group', 'group_created', '{}'
                    )
                    """
                )
            )
            assert connection.scalar(text("SELECT count(*) FROM audit_events")) == 2
            trigger_names = set(
                connection.scalars(
                    text(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type = 'trigger' AND tbl_name = 'students'
                        """
                    )
                )
            )
            assert "trg_students_reject_archived_group_insert" in trigger_names
            connection.execute(text("DELETE FROM audit_events WHERE id = 'business-event'"))
    finally:
        upgraded_engine.dispose()

    trigger_engine = create_engine(database_url)
    try:
        with (
            pytest.raises(IntegrityError, match="group_archived"),
            trigger_engine.begin() as connection,
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO students (id, group_id, name, user_role, stage)
                    VALUES ('late-student', 'group', 'Late', 'student', 'start')
                    """
                )
            )
        with trigger_engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM students")) == 1
    finally:
        trigger_engine.dispose()

    command.downgrade(config, "20261023_0003")
    downgraded_engine = create_engine(database_url)
    try:
        inspector = inspect(downgraded_engine)
        assert "audit_events" not in inspector.get_table_names()
        with downgraded_engine.connect() as connection:
            assert connection.scalar(text("SELECT login FROM users WHERE id = 'owner'")) == "owner"
            assert connection.scalar(text("SELECT name FROM groups WHERE id = 'group'")) == "Group"
            assert (
                connection.scalar(text("SELECT name FROM students WHERE id = 'student'"))
                == "Student"
            )
            assert (
                connection.scalar(
                    text(
                        """
                        SELECT count(*) FROM sqlite_master
                        WHERE type = 'trigger'
                          AND (
                              name LIKE 'trg_groups_require_active_curator%'
                              OR name = 'trg_users_preserve_group_curator_update'
                          )
                        """
                    )
                )
                == 0
            )
    finally:
        downgraded_engine.dispose()


def test_groups_students_downgrade_rejects_unsupported_audit_actions_atomically(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "business-api-downgrade-guard.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    config = alembic_config(database_url)
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, login, normalized_login, role, password_hash,
                        must_change_password, is_active, is_owner
                    ) VALUES ('owner', 'owner', 'owner', 'admin', 'hash', 0, 1, 1)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events (id, actor_user_id, action, details)
                    VALUES ('event', 'owner', 'group_created', '{}')
                    """
                )
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="cannot represent audit action group_created"):
        command.downgrade(config, "20261023_0004")

    inspected_engine = create_engine(database_url)
    try:
        inspector = inspect(inspected_engine)
        assert "version" in {column["name"] for column in inspector.get_columns("groups")}
        assert "version" in {column["name"] for column in inspector.get_columns("students")}
        with inspected_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "20261025_0005"
            )
            assert connection.scalar(text("SELECT action FROM audit_events")) == "group_created"
    finally:
        inspected_engine.dispose()


def test_user_management_migration_serializes_deactivation_and_group_assignment(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "curator-assignment-race.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    config = alembic_config(database_url)
    command.upgrade(config, "head")
    engine = create_engine(database_url, connect_args={"timeout": 5})
    try:
        with engine.begin() as connection:
            for user_id, is_owner in (("owner", 1), ("candidate", 0)):
                connection.execute(
                    text(
                        """
                        INSERT INTO users (
                            id, login, normalized_login, role, password_hash,
                            must_change_password, is_active, is_owner
                        ) VALUES (
                            :user_id, :user_id, :user_id, 'admin', 'hash', 0, 1, :is_owner
                        )
                        """
                    ),
                    {"user_id": user_id, "is_owner": is_owner},
                )
            connection.execute(
                text(
                    """
                    INSERT INTO groups (
                        id, curator_id, curator_role, name, starts_at, status
                    ) VALUES ('group', 'owner', 'admin', 'Group', '2026-01-01', 'active')
                    """
                )
            )

        barrier = Barrier(2)

        def deactivate_candidate() -> bool:
            try:
                with engine.begin() as connection:
                    barrier.wait()
                    connection.execute(
                        text("UPDATE users SET is_active = 0 WHERE id = 'candidate'")
                    )
                return True
            except IntegrityError:
                return False

        def assign_candidate() -> bool:
            try:
                with engine.begin() as connection:
                    barrier.wait()
                    connection.execute(
                        text("UPDATE groups SET curator_id = 'candidate' WHERE id = 'group'")
                    )
                return True
            except IntegrityError:
                return False

        with ThreadPoolExecutor(max_workers=2) as executor:
            deactivate_future = executor.submit(deactivate_candidate)
            assign_future = executor.submit(assign_candidate)
            outcomes = [deactivate_future.result(), assign_future.result()]

        with engine.connect() as connection:
            candidate_is_active = connection.scalar(
                text("SELECT is_active FROM users WHERE id = 'candidate'")
            )
            group_curator_id = connection.scalar(
                text("SELECT curator_id FROM groups WHERE id = 'group'")
            )
            trigger_names = set(
                connection.scalars(
                    text(
                        """
                        SELECT name FROM sqlite_master
                        WHERE type = 'trigger'
                          AND (
                              name LIKE 'trg_groups_require_active_curator%'
                              OR name = 'trg_users_preserve_group_curator_update'
                          )
                        """
                    )
                )
            )

        assert outcomes.count(True) == 1
        assert candidate_is_active or group_curator_id != "candidate"
        assert trigger_names == {
            "trg_groups_require_active_curator_insert",
            "trg_groups_require_active_curator_update",
            "trg_users_preserve_group_curator_update",
        }
    finally:
        engine.dispose()


def test_user_management_migration_rejects_existing_inactive_group_curator(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "inactive-curator-upgrade.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    config = alembic_config(database_url)
    command.upgrade(config, "20261023_0003")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, login, normalized_login, role, password_hash,
                        must_change_password, is_active, is_owner
                    ) VALUES ('inactive', 'inactive', 'inactive', 'admin', 'hash', 0, 0, 0)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO groups (
                        id, curator_id, curator_role, name, starts_at, status
                    ) VALUES ('group', 'inactive', 'admin', 'Group', '2026-01-01', 'active')
                    """
                )
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="must be reassigned to an active admin"):
        command.upgrade(config, "head")

    inspected_engine = create_engine(database_url)
    try:
        inspector = inspect(inspected_engine)
        assert "audit_events" not in inspector.get_table_names()
        with inspected_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "20261023_0003"
            )
            assert connection.scalar(text("SELECT curator_id FROM groups WHERE id = 'group'")) == (
                "inactive"
            )
    finally:
        inspected_engine.dispose()
