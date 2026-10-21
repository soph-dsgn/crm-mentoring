from functools import lru_cache
from pathlib import Path
from typing import Literal

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
