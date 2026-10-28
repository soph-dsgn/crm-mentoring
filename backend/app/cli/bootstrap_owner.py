from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import build_engine
from app.modules.auth.authorization import bootstrap_first_owner
from app.modules.auth.passwords import PasswordManager, generate_temporary_password
from app.modules.users.models import User, UserRole

BACKEND_DIR = Path(__file__).resolve().parents[2]
BOOTSTRAP_LOCK_ID = 7217318685417055441


def _migration_head(engine: Engine) -> None:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    expected = ScriptDirectory.from_config(config).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != expected:
        raise RuntimeError("Database must be migrated to the current migration head")


def bootstrap_owner(
    engine: Engine,
    manager: PasswordManager,
    login: str,
) -> tuple[User, str]:
    _migration_head(engine)
    with Session(engine, expire_on_commit=False) as database:
        try:
            if engine.dialect.name == "sqlite":
                database.execute(text("BEGIN IMMEDIATE"))
            elif engine.dialect.name == "postgresql":
                database.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_id)"),
                    {"lock_id": BOOTSTRAP_LOCK_ID},
                )
            if database.scalar(select(User.id).where(User.is_owner.is_(True)).limit(1)):
                raise RuntimeError("An owner already exists")
            temporary_password = generate_temporary_password()
            user = User(
                login=login,
                role=UserRole.ADMIN,
                password_hash=manager.hash(temporary_password),
                is_owner=False,
                is_active=True,
                must_change_password=True,
            )
            bootstrap_first_owner(user, database)
            database.add(user)
            database.flush()
            database.commit()
            return user, temporary_password
        except Exception:
            database.rollback()
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first CRM owner")
    parser.add_argument("--login", required=True)
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--confirm-first-owner", action="store_true")
    args = parser.parse_args()
    if not args.confirm_first_owner:
        parser.error("--confirm-first-owner is required")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("First-owner credentials require an interactive terminal")

    settings = get_settings()
    database_name = make_url(settings.database_url).database
    if not database_name or args.confirm_database != database_name:
        parser.error("--confirm-database must match the configured database name")
    manager = PasswordManager(
        time_cost=settings.auth_argon2_time_cost,
        memory_cost=settings.auth_argon2_memory_cost,
        parallelism=settings.auth_argon2_parallelism,
        minimum_length=settings.auth_password_min_length,
    )
    engine = build_engine(
        settings.database_url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=settings.database_pool_timeout_seconds,
        connect_timeout=settings.database_connect_timeout_seconds,
    )
    try:
        user, temporary_password = bootstrap_owner(engine, manager, args.login)
    finally:
        engine.dispose()
    print(f"Owner login: {user.login}")
    print(f"Temporary password (shown once): {temporary_password}")
    print("Sign in and change this password immediately.")


if __name__ == "__main__":
    main()
