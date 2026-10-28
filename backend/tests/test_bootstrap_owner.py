from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.cli.bootstrap_owner import bootstrap_owner
from app.core.config import Settings
from app.db.session import build_engine, get_db
from app.main import create_app
from app.modules.auth.passwords import LoginFormatError, PasswordManager
from app.modules.users.models import User

BACKEND_DIR = Path(__file__).resolve().parents[1]


def migrated_engine(tmp_path: Path) -> Engine:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'bootstrap.db').as_posix()}"
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["database_url"] = database_url
    command.upgrade(config, "head")
    return build_engine(database_url)


def password_manager() -> PasswordManager:
    return PasswordManager(time_cost=1, memory_cost=1024, parallelism=1)


def test_first_owner_is_created_with_one_time_temporary_password(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        user, temporary_password = bootstrap_owner(engine, password_manager(), "first.owner")

        assert user.login == "first.owner"
        assert user.is_owner is True
        assert user.is_active is True
        assert user.must_change_password is True
        assert password_manager().verify(temporary_password, user.password_hash)
        assert temporary_password not in user.password_hash

        factory = sessionmaker(bind=engine, expire_on_commit=False)
        settings = Settings(
            environment="test",
            database_url=str(engine.url),
            auth_argon2_time_cost=1,
            auth_argon2_memory_cost=1024,
            auth_argon2_parallelism=1,
            _env_file=None,
        )
        app = create_app(settings, database_engine=engine)

        def override_db():
            with factory() as database:
                yield database

        app.dependency_overrides[get_db] = override_db
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={"login": user.login, "password": temporary_password},
                headers={"Origin": "http://testserver"},
            )
        assert response.status_code == 200
        assert response.json()["must_change_password"] is True
    finally:
        engine.dispose()


def test_repeated_and_concurrent_bootstrap_create_at_most_one_owner(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:

        def attempt(login: str) -> str:
            try:
                bootstrap_owner(engine, password_manager(), login)
                return "created"
            except RuntimeError as error:
                assert str(error) == "An owner already exists"
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(attempt, ("owner.one", "owner.two")))

        assert sorted(outcomes) == ["created", "rejected"]
        with Session(engine) as database:
            assert database.scalar(select(func.count(User.id)).where(User.is_owner.is_(True))) == 1
    finally:
        engine.dispose()


def test_bootstrap_rejects_invalid_login_and_unmigrated_database(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with pytest.raises(LoginFormatError):
            bootstrap_owner(engine, password_manager(), "invalid login")
    finally:
        engine.dispose()

    unmigrated = build_engine(f"sqlite+pysqlite:///{(tmp_path / 'empty.db').as_posix()}")
    try:
        with pytest.raises(RuntimeError, match="migration head"):
            bootstrap_owner(unmigrated, password_manager(), "first.owner")
    finally:
        unmigrated.dispose()


def test_failed_bootstrap_rolls_back(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with Session(engine) as database, database.begin():
            database.add(
                User(
                    login="duplicate",
                    role="admin",
                    password_hash="existing-hash",
                    is_active=True,
                    is_owner=False,
                )
            )

        with pytest.raises(IntegrityError):
            bootstrap_owner(engine, password_manager(), "duplicate")

        with Session(engine) as database:
            assert database.scalar(select(func.count(User.id)).where(User.is_owner.is_(True))) == 0
    finally:
        engine.dispose()
