from pathlib import Path

from sqlalchemy import text

from app.db.session import build_engine


def test_sqlite_connection() -> None:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
            assert connection.scalar(text("PRAGMA foreign_keys")) == 1
    finally:
        engine.dispose()


def test_sqlite_foreign_keys_are_enabled_for_every_connection(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'foreign-keys.db').as_posix()}"
    engine = build_engine(database_url)
    try:
        with engine.connect() as first_connection, engine.connect() as second_connection:
            assert first_connection.scalar(text("PRAGMA foreign_keys")) == 1
            assert second_connection.scalar(text("PRAGMA foreign_keys")) == 1
    finally:
        engine.dispose()
