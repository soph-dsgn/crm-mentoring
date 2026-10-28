from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine, get_db
from app.main import create_app
from app.modules.auth.passwords import PasswordManager
from app.modules.users.models import User, UserRole


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "database_url": "postgresql+psycopg://crm:secret@db.internal/kuratorskaya",
        "permitted_hosts": ["api.example.com"],
        "frontend_origins": ["https://app.example.com"],
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"database_url": "sqlite+pysqlite:///production.db"}, "PostgreSQL"),
        ({"debug": True}, "debug"),
        ({"permitted_hosts": []}, "permitted hosts"),
        ({"permitted_hosts": ["*"]}, "wildcard"),
        ({"frontend_origins": []}, "frontend origins"),
        ({"frontend_origins": ["*"]}, "wildcard"),
        ({"frontend_origins": ["http://app.example.com"]}, "HTTPS"),
        ({"trusted_proxy_ips": ["not-an-ip"]}, "proxy"),
    ],
)
def test_insecure_production_settings_are_rejected(
    override: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        production_settings(**override)


def test_development_defaults_remain_compatible() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.database_url.startswith("sqlite")


def test_production_validation_error_hides_database_credentials() -> None:
    with pytest.raises(ValidationError) as failure:
        production_settings(
            database_url="sqlite+pysqlite:///production.db?password=do-not-log-this"
        )

    assert "do-not-log-this" not in str(failure.value)


def test_production_app_restricts_docs_hosts_origins_and_forwarded_headers() -> None:
    app = create_app(production_settings())

    with TestClient(app, base_url="https://api.example.com") as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/live", headers={"Host": "evil.example"}).status_code == 400
        assert (
            client.get("/health/live", headers={"X-Forwarded-Host": "api.example.com"}).status_code
            == 400
        )
        preflight = client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert preflight.headers["access-control-allow-origin"] == "https://app.example.com"
        assert preflight.headers["access-control-allow-credentials"] == "true"


def test_production_login_uses_secure_cookies_and_configured_origin(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'cookies.db').as_posix()}"
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = production_settings(
        auth_argon2_time_cost=1,
        auth_argon2_memory_cost=1024,
        auth_argon2_parallelism=1,
    )
    app = create_app(settings, database_engine=engine)

    def override_db() -> Iterator[Session]:
        with factory() as database:
            yield database

    app.dependency_overrides[get_db] = override_db
    manager = PasswordManager(time_cost=1, memory_cost=1024, parallelism=1)
    with factory.begin() as database:
        database.add(
            User(
                login="owner",
                role=UserRole.ADMIN,
                password_hash=manager.hash("correct horse battery staple"),
                is_active=True,
                is_owner=True,
                must_change_password=False,
            )
        )

    with TestClient(app, base_url="https://api.example.com") as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"login": "owner", "password": "correct horse battery staple"},
            headers={"Origin": "https://app.example.com"},
        )

    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    assert all("Secure" in value and "SameSite=lax" in value for value in cookies)
    assert "HttpOnly" in cookies[0]
    assert "HttpOnly" not in cookies[1]


def test_production_internal_errors_are_sanitized() -> None:
    app = create_app(production_settings())

    @app.get("/test/error")
    def error() -> None:
        raise RuntimeError("secret database detail")

    with TestClient(
        app,
        base_url="https://api.example.com",
        raise_server_exceptions=False,
    ) as client:
        response = client.get("/test/error")

    assert response.status_code == 500
    assert "secret database detail" not in response.text


class BrokenEngine:
    disposed = False

    def connect(self) -> None:
        raise OperationalError("SELECT 1", {}, RuntimeError("database unavailable"))

    def dispose(self) -> None:
        self.disposed = True


def test_liveness_does_not_query_database_and_readiness_fails_safely() -> None:
    engine = BrokenEngine()
    settings = Settings(
        environment="test", database_url="sqlite+pysqlite:///:memory:", _env_file=None
    )
    app = create_app(settings, database_engine=engine)

    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {
            "error": {
                "code": "not_ready",
                "message": "Required dependency is unavailable",
                "details": {},
            }
        }

    assert engine.disposed is True


def test_readiness_uses_lightweight_database_probe() -> None:
    engine: Engine = build_engine("sqlite+pysqlite:///:memory:")
    settings = Settings(
        environment="test", database_url="sqlite+pysqlite:///:memory:", _env_file=None
    )
    app = create_app(settings, database_engine=engine)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").json() == {"status": "ok"}

    assert engine.pool.status().startswith("StaticPool")
