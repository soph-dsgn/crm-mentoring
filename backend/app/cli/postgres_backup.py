from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from subprocess import CompletedProcess

from sqlalchemy import inspect, text
from sqlalchemy.engine import URL, make_url

from app.core.config import get_settings
from app.db.session import build_engine

APP_VERSION = "0.1.0"
Runner = Callable[..., CompletedProcess[str]]


class BackupError(RuntimeError):
    pass


def _subprocess_runner(command: list[str], *, env: dict[str, str]) -> CompletedProcess[str]:
    return subprocess.run(command, env=env, capture_output=True, text=True, check=False)


def _postgres_url(database_url: str) -> URL:
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql" or not url.database:
        raise BackupError("PostgreSQL database URL is required")
    return url


def _postgres_environment(url: URL) -> dict[str, str]:
    environment = os.environ.copy()
    values = {
        "PGHOST": url.host or "",
        "PGPORT": str(url.port or 5432),
        "PGDATABASE": url.database or "",
        "PGUSER": url.username or "",
        "PGPASSWORD": url.password or "",
    }
    sslmode = url.query.get("sslmode")
    if sslmode:
        values["PGSSLMODE"] = str(sslmode)
    environment.update(values)
    return environment


def _execute(
    command: list[str],
    environment: dict[str, str],
    runner: Runner,
    error_message: str,
) -> CompletedProcess[str]:
    result = runner(command, env=environment)
    if result.returncode != 0:
        raise BackupError(error_message)
    return result


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata_path(archive: Path) -> Path:
    return archive.with_name(f"{archive.name}.metadata.json")


def _database_revision(database_url: str) -> str:
    engine = build_engine(database_url, pool_size=1, max_overflow=0)
    try:
        with engine.connect() as connection:
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        engine.dispose()
    if not revision:
        raise BackupError("Database migration revision is unavailable")
    return str(revision)


def create_backup(
    database_url: str,
    archive: Path,
    *,
    runner: Runner = _subprocess_runner,
    migration_revision: str | None = None,
) -> dict[str, object]:
    url = _postgres_url(database_url)
    metadata_path = _metadata_path(archive)
    archive.parent.mkdir(parents=True, exist_ok=True)
    lock_path = archive.with_name(f".{archive.name}.lock")
    try:
        lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise BackupError("Backup output is already being created") from error
    os.close(lock_descriptor)
    environment = _postgres_environment(url)
    temporary_archive: Path | None = None
    temporary_metadata: Path | None = None
    installed_archive = False
    try:
        if archive.exists() or metadata_path.exists():
            raise BackupError("Backup output already exists")
        with tempfile.NamedTemporaryFile(
            prefix=f".{archive.name}.", suffix=".partial", dir=archive.parent, delete=False
        ) as temporary:
            temporary_archive = Path(temporary.name)
        os.chmod(temporary_archive, 0o600)
        version = _execute(
            ["pg_dump", "--version"], environment, runner, "pg_dump version check failed"
        ).stdout.strip()
        _execute(
            [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                f"--file={temporary_archive}",
            ],
            environment,
            runner,
            "pg_dump failed",
        )
        _execute(
            ["pg_restore", "--list", str(temporary_archive)],
            environment,
            runner,
            "Backup archive verification failed",
        )
        metadata: dict[str, object] = {
            "format": "kuratorskaya-postgresql-custom",
            "version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "sha256": _checksum(temporary_archive),
            "application_version": APP_VERSION,
            "migration_revision": migration_revision or _database_revision(database_url),
            "pg_dump_version": version,
        }
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{metadata_path.name}.",
            suffix=".partial",
            dir=archive.parent,
            delete=False,
        ) as temporary:
            json.dump(metadata, temporary, sort_keys=True)
            temporary.write("\n")
            temporary_metadata = Path(temporary.name)
        os.chmod(temporary_metadata, 0o600)
        if archive.exists() or metadata_path.exists():
            raise BackupError("Backup output already exists")
        os.replace(temporary_archive, archive)
        installed_archive = True
        temporary_archive = None
        os.replace(temporary_metadata, metadata_path)
        temporary_metadata = None
        return metadata
    finally:
        for path in (temporary_archive, temporary_metadata):
            if path is not None:
                path.unlink(missing_ok=True)
        if installed_archive and not metadata_path.exists():
            archive.unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)


def _target_is_empty(database_url: str) -> bool:
    engine = build_engine(database_url, pool_size=1, max_overflow=0)
    try:
        return not inspect(engine).get_table_names()
    finally:
        engine.dispose()


def restore_backup(
    database_url: str,
    archive: Path,
    *,
    environment: str,
    confirmed: bool,
    runner: Runner = _subprocess_runner,
    target_is_empty: Callable[[str], bool] = _target_is_empty,
    revision_reader: Callable[[str], str] = _database_revision,
) -> None:
    if not confirmed:
        raise BackupError("Restore requires explicit confirmation")
    if environment == "production":
        raise BackupError("Direct production restore is prohibited")
    url = _postgres_url(database_url)
    if not url.database.lower().endswith(("_restore", "_test")):
        raise BackupError("Restore target must be a disposable _restore or _test database")
    metadata_path = _metadata_path(archive)
    if not archive.is_file() or not metadata_path.is_file():
        raise BackupError("Backup archive and metadata are required")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BackupError("Backup metadata is invalid") from error
    if metadata.get("format") != "kuratorskaya-postgresql-custom" or metadata.get("version") != 1:
        raise BackupError("Backup metadata is unsupported")
    if metadata.get("sha256") != _checksum(archive):
        raise BackupError("Backup checksum does not match")
    if not target_is_empty(database_url):
        raise BackupError("Restore target database must be empty")
    postgres_environment = _postgres_environment(url)
    _execute(
        ["pg_restore", "--list", str(archive)],
        postgres_environment,
        runner,
        "Backup archive verification failed",
    )
    _execute(
        [
            "pg_restore",
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-privileges",
            f"--dbname={url.database}",
            str(archive),
        ],
        postgres_environment,
        runner,
        "pg_restore failed",
    )
    if revision_reader(database_url) != metadata.get("migration_revision"):
        raise BackupError("Restored migration revision does not match backup metadata")


def main() -> None:
    parser = argparse.ArgumentParser(description="PostgreSQL operational backup and restore")
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--output", required=True, type=Path)
    backup.add_argument("--confirm-database", required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--archive", required=True, type=Path)
    restore.add_argument("--confirm-target-database", required=True)
    restore.add_argument("--confirm-destructive-restore", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if args.command == "backup":
        database_name = make_url(settings.database_url).database
        if args.confirm_database != database_name:
            parser.error("--confirm-database must match the configured database name")
        print(json.dumps(create_backup(settings.database_url, args.output), sort_keys=True))
    else:
        target_url = os.environ.get("KURATORSKAYA_RESTORE_DATABASE_URL")
        if not target_url:
            parser.error("KURATORSKAYA_RESTORE_DATABASE_URL is required")
        target_name = make_url(target_url).database
        if args.confirm_target_database != target_name:
            parser.error("--confirm-target-database must match the restore database name")
        restore_backup(
            target_url,
            args.archive,
            environment=settings.environment,
            confirmed=args.confirm_destructive_restore,
        )
        print(json.dumps({"restored": True}, sort_keys=True))


if __name__ == "__main__":
    main()
