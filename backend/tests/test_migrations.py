from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

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
            "groups",
            "students",
            "users",
        }
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
