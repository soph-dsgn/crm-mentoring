from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

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
            "auth_sessions",
            "groups",
            "login_attempts",
            "students",
            "users",
        }
        assert {column["name"] for column in inspector.get_columns("users")} >= {"normalized_login"}
        assert {column["name"] for column in inspector.get_columns("groups")} >= {
            "id",
            "curator_id",
            "name",
            "status",
        }
        assert {column["name"] for column in inspector.get_columns("students")} >= {
            "id",
            "group_id",
            "user_id",
            "name",
        }
        assert {index["name"] for index in inspector.get_indexes("groups")} >= {
            "ix_groups_curator_id",
            "ix_groups_status",
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
