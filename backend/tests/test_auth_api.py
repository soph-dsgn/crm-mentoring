from __future__ import annotations

import base64
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from typing import Annotated

import pytest
from argon2 import PasswordHasher
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.dml import Update

from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine, get_db
from app.main import create_app
from app.modules.auth.dependencies import hash_secret, require_business_user
from app.modules.auth.models import AuthSession, LoginAttempt
from app.modules.auth.passwords import PasswordManager
from app.modules.users.models import User, UserRole

PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "new correct horse battery staple"


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 10, 22, 12, 0, 0)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: int) -> None:
        self.value += timedelta(**kwargs)


@pytest.fixture
def auth_context(tmp_path) -> Iterator[tuple[TestClient, sessionmaker[Session], MutableClock]]:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'auth.db').as_posix()}"
    engine: Engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        environment="test",
        database_url=database_url,
        auth_argon2_time_cost=1,
        auth_argon2_memory_cost=1024,
        auth_argon2_parallelism=1,
        auth_login_max_failures_per_login=2,
        auth_login_max_failures_per_client=3,
        _env_file=None,
    )
    application = create_app(settings)
    clock = MutableClock()
    application.state.clock = clock

    def override_db() -> Iterator[Session]:
        with factory() as database_session:
            yield database_session

    application.dependency_overrides[get_db] = override_db

    @application.get("/test/protected")
    def protected(
        _: Annotated[User, Depends(require_business_user)],
    ) -> dict[str, bool]:
        return {"ok": True}

    with TestClient(application) as client:
        yield client, factory, clock
    Base.metadata.drop_all(engine)
    engine.dispose()


def add_user(
    client: TestClient,
    factory: sessionmaker[Session],
    *,
    login: str = "curator",
    password: str = PASSWORD,
    is_active: bool = True,
    must_change_password: bool = False,
) -> User:
    manager: PasswordManager = client.app.state.password_manager
    user = User(
        login=login,
        normalized_login=login.casefold(),
        role=UserRole.ADMIN,
        password_hash=manager.hash(password),
        is_active=is_active,
        must_change_password=must_change_password,
    )
    with factory.begin() as database_session:
        database_session.add(user)
    return user


def login(client: TestClient, login_value: str = "curator", password: str = PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        json={"login": login_value, "password": password},
        headers={"Origin": "http://testserver"},
    )


def csrf_headers(client: TestClient) -> dict[str, str]:
    return {
        "Origin": "http://testserver",
        "X-CSRF-Token": client.cookies.get("kuratorskaya_csrf"),
    }


def test_successful_login_persists_only_token_hash_and_safe_response(auth_context) -> None:
    client, factory, _ = auth_context
    user = add_user(client, factory)

    response = login(client, "  CURATOR ")

    assert response.status_code == 200
    assert response.json() == {
        "id": user.id,
        "login": "curator",
        "role": "admin",
        "is_owner": False,
        "must_change_password": False,
        "is_active": True,
    }
    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header
    session_token = client.cookies.get("kuratorskaya_session")
    decoded_token = base64.urlsafe_b64decode(session_token + "=" * (-len(session_token) % 4))
    assert len(decoded_token) == 32
    with factory() as database_session:
        stored = database_session.scalar(select(AuthSession))
        assert stored is not None
        assert stored.token_hash != session_token
        assert session_token not in stored.token_hash
        assert stored.csrf_token_hash != client.cookies.get("kuratorskaya_csrf")
    assert "password_hash" not in response.json()
    assert "session_token" not in response.json()


def test_login_replaces_untrusted_session_cookie(auth_context) -> None:
    client, factory, _ = auth_context
    add_user(client, factory)
    client.cookies.set(
        "kuratorskaya_session",
        "attacker-controlled-token",
        domain="testserver.local",
        path="/",
    )

    assert login(client).status_code == 200

    replacement = client.cookies.get("kuratorskaya_session")
    assert replacement != "attacker-controlled-token"
    with factory() as database_session:
        sessions = database_session.scalars(select(AuthSession)).all()
        assert len(sessions) == 1
        assert sessions[0].token_hash != "attacker-controlled-token"
        assert sessions[0].token_hash != hash_secret("attacker-controlled-token")


def test_successful_login_persists_rehashed_password(auth_context) -> None:
    client, factory, _ = auth_context
    old_hash = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=2).hash(PASSWORD)
    user = User(
        login="curator",
        role=UserRole.ADMIN,
        password_hash=old_hash,
        is_active=True,
        must_change_password=False,
    )
    with factory.begin() as database_session:
        database_session.add(user)

    assert login(client).status_code == 200

    with factory() as database_session:
        persisted_hash = database_session.get(User, user.id).password_hash
        assert persisted_hash != old_hash
        assert client.app.state.password_manager.verify(PASSWORD, persisted_hash)
        assert PASSWORD not in persisted_hash


def test_database_rejects_logins_that_differ_only_by_case(auth_context) -> None:
    client, factory, _ = auth_context
    add_user(client, factory)

    with pytest.raises(IntegrityError), factory.begin() as database_session:
        database_session.execute(
            text(
                """
                INSERT INTO users (id, login, normalized_login, role, password_hash)
                VALUES ('duplicate', 'CURATOR', 'curator', 'admin', 'hash')
                """
            )
        )


def test_production_session_cookie_is_secure(auth_context) -> None:
    client, factory, _ = auth_context
    add_user(client, factory)
    client.app.state.settings.environment = "production"
    production_client = TestClient(client.app, base_url="https://testserver")

    response = production_client.post(
        "/api/v1/auth/login",
        json={"login": "curator", "password": PASSWORD},
        headers={"Origin": "https://testserver"},
    )

    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()
    logout_response = production_client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": production_client.cookies.get("kuratorskaya_csrf")},
    )
    assert logout_response.status_code == 204
    assert all(
        "secure" in header.lower() for header in logout_response.headers.get_list("set-cookie")
    )
    production_client.close()


def test_login_failures_are_generic_and_inactive_user_cannot_login(auth_context) -> None:
    client, factory, _ = auth_context
    add_user(client, factory, is_active=False)

    wrong = login(client, password="not the password")
    missing = login(client, login_value="missing", password="not the password")
    inactive = login(client)

    assert wrong.status_code == missing.status_code == inactive.status_code == 401
    assert wrong.json() == missing.json() == inactive.json()
    assert wrong.json() == {
        "error": {
            "code": "invalid_credentials",
            "message": "Invalid credentials",
            "details": {},
        }
    }
    with factory() as database_session:
        assert database_session.scalar(select(func.count()).select_from(AuthSession)) == 0
        assert database_session.scalar(select(func.count()).select_from(LoginAttempt)) == 3


def test_me_requires_a_live_session_and_updates_last_activity(auth_context) -> None:
    client, factory, clock = auth_context
    user = add_user(client, factory)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client).status_code == 200
    clock.advance(hours=1)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["id"] == user.id
    with factory() as database_session:
        assert database_session.scalar(select(AuthSession)).last_activity_at == clock.value


def test_existing_session_is_rejected_after_user_deactivation(auth_context) -> None:
    client, factory, _ = auth_context
    user = add_user(client, factory)
    assert login(client).status_code == 200
    with factory.begin() as database_session:
        database_session.get(User, user.id).is_active = False

    assert client.get("/api/v1/auth/me").status_code == 401


def test_revoked_idle_and_absolute_expired_sessions_are_invalid(auth_context) -> None:
    client, factory, clock = auth_context
    add_user(client, factory)
    assert login(client).status_code == 200

    with factory.begin() as database_session:
        stored = database_session.scalar(select(AuthSession))
        stored.revoked_at = clock.value
    assert client.get("/api/v1/auth/me").status_code == 401

    client.cookies.clear()
    assert login(client).status_code == 200
    clock.advance(days=7)
    assert client.get("/api/v1/auth/me").status_code == 401

    client.cookies.clear()
    clock.value = datetime(2026, 10, 22, 12, 0, 0)
    assert login(client).status_code == 200
    clock.advance(days=30)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_requires_csrf_revokes_session_and_is_repeatable(auth_context) -> None:
    client, factory, clock = auth_context
    add_user(client, factory)
    assert login(client).status_code == 200

    assert client.post("/api/v1/auth/logout").status_code == 403
    response = client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert response.status_code == 204
    with factory() as database_session:
        assert database_session.scalar(select(AuthSession)).revoked_at == clock.value

    assert client.post("/api/v1/auth/logout").status_code == 204


def test_csrf_token_cannot_be_reused_between_sessions(auth_context) -> None:
    first_client, factory, _ = auth_context
    add_user(first_client, factory)
    second_client = TestClient(first_client.app)
    assert login(first_client).status_code == 200
    assert login(second_client).status_code == 200
    first_csrf = first_client.cookies.get("kuratorskaya_csrf")
    second_client.cookies.set("kuratorskaya_csrf", first_csrf)

    response = second_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers={"X-CSRF-Token": first_csrf},
    )

    assert response.status_code == 403
    second_client.close()


def test_change_password_revokes_all_sessions_and_clears_requirement(auth_context) -> None:
    client, factory, _ = auth_context
    user = add_user(client, factory, must_change_password=True)
    second_client = TestClient(client.app)
    assert login(client).status_code == 200
    assert login(second_client).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.get("/test/protected").status_code == 403

    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=csrf_headers(client),
    )

    assert response.status_code == 204
    assert client.cookies.get("kuratorskaya_session") is None
    assert second_client.get("/api/v1/auth/me").status_code == 401
    with factory() as database_session:
        persisted_user = database_session.get(User, user.id)
        assert persisted_user.must_change_password is False
        assert client.app.state.password_manager.verify(NEW_PASSWORD, persisted_user.password_hash)
        sessions = database_session.scalars(select(AuthSession)).all()
        assert len(sessions) == 2
        assert all(item.revoked_at is not None for item in sessions)
    second_client.close()


def test_password_change_and_logout_each_use_one_commit(auth_context, monkeypatch) -> None:
    client, factory, _ = auth_context
    add_user(client, factory)
    assert login(client).status_code == 200
    original_commit = Session.commit
    commit_count = 0

    def counting_commit(database_session: Session) -> None:
        nonlocal commit_count
        commit_count += 1
        original_commit(database_session)

    monkeypatch.setattr(Session, "commit", counting_commit)
    changed = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=csrf_headers(client),
    )
    assert changed.status_code == 204
    assert commit_count == 1

    assert login(client, password=NEW_PASSWORD).status_code == 200
    commit_count = 0
    logged_out = client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert logged_out.status_code == 204
    assert commit_count == 1


def test_password_change_rolls_back_password_and_revocations_together(
    auth_context, monkeypatch
) -> None:
    client, factory, _ = auth_context
    user = add_user(client, factory, must_change_password=True)
    assert login(client).status_code == 200
    original_execute = Session.execute

    def fail_session_revocation(database_session: Session, statement, *args, **kwargs):
        if isinstance(statement, Update):
            raise RuntimeError("simulated revocation failure")
        return original_execute(database_session, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", fail_session_revocation)
    with pytest.raises(RuntimeError, match="simulated revocation failure"):
        client.post(
            "/api/v1/auth/change-password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=csrf_headers(client),
        )

    with factory() as database_session:
        persisted_user = database_session.get(User, user.id)
        assert persisted_user.must_change_password is True
        assert client.app.state.password_manager.verify(PASSWORD, persisted_user.password_hash)
        assert database_session.scalar(select(AuthSession)).revoked_at is None


def test_change_password_rejects_bad_current_password_and_missing_csrf(auth_context) -> None:
    client, factory, _ = auth_context
    user = add_user(client, factory)
    assert login(client).status_code == 200

    no_csrf = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    bad_current = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrong", "new_password": NEW_PASSWORD},
        headers=csrf_headers(client),
    )

    assert no_csrf.status_code == 403
    assert bad_current.status_code == 401

    too_short = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "too short"},
        headers=csrf_headers(client),
    )
    assert too_short.status_code == 422
    assert "too short" not in too_short.text
    with factory() as database_session:
        persisted_user = database_session.get(User, user.id)
        assert client.app.state.password_manager.verify(PASSWORD, persisted_user.password_hash)
        assert database_session.scalar(select(AuthSession)).revoked_at is None


def test_change_password_rejects_form_content_type_without_state_change(auth_context) -> None:
    client, factory, _ = auth_context
    user = add_user(client, factory)
    assert login(client).status_code == 200

    response = client.post(
        "/api/v1/auth/change-password",
        data={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=csrf_headers(client),
    )

    assert response.status_code == 422
    with factory() as database_session:
        persisted_user = database_session.get(User, user.id)
        assert client.app.state.password_manager.verify(PASSWORD, persisted_user.password_hash)
        assert database_session.scalar(select(AuthSession)).revoked_at is None


def test_rate_limit_normalizes_login_and_limits_distributed_accounts(auth_context) -> None:
    client, factory, clock = auth_context
    add_user(client, factory)

    assert login(client, "CURATOR", "wrong").status_code == 401
    assert login(client, " curator ", "wrong").status_code == 401
    assert login(client, "Curator", "wrong").status_code == 429

    clock.advance(minutes=16)
    for index, login_value in enumerate(("first", "second", "third")):
        response = client.post(
            "/api/v1/auth/login",
            json={"login": login_value, "password": "wrong"},
            headers={
                "Origin": "http://testserver",
                "X-Forwarded-For": f"203.0.113.{index}",
            },
        )
        assert response.status_code == 401
    fourth = client.post(
        "/api/v1/auth/login",
        json={"login": "fourth", "password": "wrong"},
        headers={"Origin": "http://testserver", "X-Forwarded-For": "198.51.100.4"},
    )
    assert fourth.status_code == 429
    with factory() as database_session:
        attempts = database_session.scalars(select(LoginAttempt)).all()
        assert len(attempts) == 3
        assert all("curator" not in attempt.login_key for attempt in attempts)


def test_concurrent_login_failures_do_not_bypass_login_limit(auth_context) -> None:
    client, factory, _ = auth_context
    add_user(client, factory)
    client.app.state.settings.auth_login_max_failures_per_login = 1
    barrier = Barrier(2)

    def attempt(test_client: TestClient) -> int:
        barrier.wait()
        return login(test_client, password="wrong").status_code

    with (
        TestClient(client.app) as first_client,
        TestClient(client.app) as second_client,
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        first_attempt = executor.submit(attempt, first_client)
        second_attempt = executor.submit(attempt, second_client)
        statuses = sorted((first_attempt.result(), second_attempt.result()))

    assert statuses == [401, 429]


def test_cross_site_login_is_rejected(auth_context) -> None:
    client, factory, _ = auth_context
    add_user(client, factory)

    response = client.post(
        "/api/v1/auth/login",
        json={"login": "curator", "password": PASSWORD},
        headers={"Origin": "https://attacker.example"},
    )

    assert response.status_code == 403


def test_fetch_metadata_blocks_cross_site_and_missing_origin_is_supported(auth_context) -> None:
    client, factory, _ = auth_context
    add_user(client, factory)

    blocked = client.post(
        "/api/v1/auth/login",
        json={"login": "curator", "password": PASSWORD},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    allowed = client.post(
        "/api/v1/auth/login",
        json={"login": "curator", "password": PASSWORD},
    )

    assert blocked.status_code == 403
    assert allowed.status_code == 200
    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": client.cookies.get("kuratorskaya_csrf")},
    )
    assert logout_response.status_code == 204
