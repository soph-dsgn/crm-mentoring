from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="KURATORSKAYA_",
        extra="ignore",
    )

    app_name: str = "кураторская API"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    database_url: str = "sqlite+pysqlite:///./kuratorskaya.db"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
