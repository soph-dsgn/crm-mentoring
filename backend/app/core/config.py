from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="KURATORSKAYA_",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = "кураторская API"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    database_url: str = "sqlite+pysqlite:///./kuratorskaya.db"
    database_pool_size: int = Field(default=3, ge=1, le=10)
    database_max_overflow: int = Field(default=1, ge=0, le=10)
    database_pool_timeout_seconds: int = Field(default=30, gt=0, le=120)
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    permitted_hosts: list[str] = Field(default_factory=list)
    frontend_origins: list[str] = Field(default_factory=list)
    trusted_proxy_ips: list[str] = Field(default_factory=list)
    auth_password_min_length: int = Field(default=12, ge=12)
    auth_argon2_time_cost: int = Field(default=3, gt=0)
    auth_argon2_memory_cost: int = Field(default=65536, ge=1024)
    auth_argon2_parallelism: int = Field(default=4, gt=0)
    auth_session_idle_days: int = Field(default=7, gt=0)
    auth_session_absolute_days: int = Field(default=30, gt=0)
    auth_session_cookie_name: str = "kuratorskaya_session"
    auth_csrf_cookie_name: str = "kuratorskaya_csrf"
    auth_login_window_minutes: int = Field(default=15, gt=0)
    auth_login_max_failures_per_login: int = Field(default=5, gt=0)
    auth_login_max_failures_per_client: int = Field(default=20, gt=0)

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.environment != "production":
            return self
        if make_url(self.database_url).get_backend_name() != "postgresql":
            raise ValueError("Production requires PostgreSQL")
        if self.debug:
            raise ValueError("Production debug mode must be disabled")
        if not self.permitted_hosts:
            raise ValueError("Production permitted hosts must be explicit")
        if any(not host.strip() or "*" in host for host in self.permitted_hosts):
            raise ValueError("Production host wildcard is prohibited")
        if not self.frontend_origins:
            raise ValueError("Production frontend origins must be explicit")
        for origin in self.frontend_origins:
            parts = urlsplit(origin)
            if origin == "*" or "*" in origin:
                raise ValueError("Production origin wildcard is prohibited")
            if (
                parts.scheme != "https"
                or not parts.netloc
                or parts.username
                or parts.password
                or parts.path not in ("", "/")
                or parts.query
                or parts.fragment
            ):
                raise ValueError("Production frontend origins must be HTTPS origins")
        try:
            for value in self.trusted_proxy_ips:
                ip_address(value)
        except ValueError as error:
            raise ValueError("Production trusted proxy values must be IP addresses") from error
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
