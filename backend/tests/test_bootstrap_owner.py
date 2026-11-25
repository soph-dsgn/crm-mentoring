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

from app.cli.bootstrap_owner import bootstrap_owner, recover_owner
from app.core.config import Settings
from app.db.session import build_engine, get_db
from app.main import create_app
from app.modules.auth.passwords import LoginFormatError, PasswordManager
from app.modules.users.audit import AuditAction, AuditEvent
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


def test_operator_recovery_preserves_owner_identity_and_audits_rotation(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        manager = password_manager()
        owner, original = bootstrap_owner(engine, manager, "first.owner")
        with pytest.raises(RuntimeError, match="No active owner"):
            recover_owner(engine, manager, "another.user")

        recovered, replacement = recover_owner(engine, manager, owner.login)
        assert recovered.id == owner.id
        assert recovered.is_owner and recovered.must_change_password
        assert manager.verify(replacement, recovered.password_hash)
        assert not manager.verify(original, recovered.password_hash)
        with Session(engine) as database:
            event = database.scalar(select(AuditEvent))
            assert event.action == AuditAction.OWNER_CREDENTIAL_RECOVERED
            assert event.target_user_id == owner.id
    finally:
        engine.dispose()


def test_cli_explains_existing_owner_instead_of_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.cli import bootstrap_owner as cli

    engine = migrated_engine(tmp_path)
    try:
        bootstrap_owner(engine, password_manager(), "owner.one")
    finally:
        engine.dispose()
    settings = Settings(
        environment="test",
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'bootstrap.db').as_posix()}",
        auth_argon2_time_cost=1,
        auth_argon2_memory_cost=1024,
        auth_argon2_parallelism=1,
        _env_file=None,
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "bootstrap_owner",
            "--login",
            "owner.two",
            "--confirm-database",
            (tmp_path / "bootstrap.db").as_posix(),
            "--confirm-first-owner",
        ],
    )

    with pytest.raises(SystemExit) as exit_info:
        cli.main()

    assert exit_info.value.code == 2
    error_output = capsys.readouterr().err
    assert "An owner already exists" in error_output
    assert "--confirm-owner-recovery" in error_output
    assert "Traceback" not in error_output
