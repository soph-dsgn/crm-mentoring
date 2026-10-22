from collections.abc import Iterator

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import build_engine


@pytest.fixture
def engine() -> Iterator[Engine]:
    database_engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(database_engine)
    try:
        yield database_engine
    finally:
        Base.metadata.drop_all(database_engine)
        database_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as database_session:
        yield database_session
