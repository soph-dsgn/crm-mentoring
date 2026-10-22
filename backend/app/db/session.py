from collections.abc import Iterator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


def build_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    connect_args = {"check_same_thread": False} if url.get_backend_name() == "sqlite" else {}
    engine_options: dict[str, Any] = {}
    if url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:"):
        engine_options["poolclass"] = StaticPool
    database_engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        **engine_options,
    )

    if url.get_backend_name() == "sqlite":

        @event.listens_for(database_engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return database_engine


engine = build_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
