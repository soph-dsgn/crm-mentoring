from __future__ import annotations

import hashlib
import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from app.cli import postgres_backup as backup_module
from app.cli.postgres_backup import BackupError, create_backup, restore_backup

DATABASE_URL = "postgresql+psycopg://crm:top-secret@db.internal/kuratorskaya_test"


class FakeRunner:
    def __init__(self, *, fail_command: str | None = None) -> None:
        self.fail_command = fail_command
        self.calls: list[tuple[list[str], dict[str, str]]] = []

    def __call__(self, command: list[str], *, env: dict[str, str]) -> CompletedProcess[str]:
        self.calls.append((command, env))
        if command[1:] == ["--version"]:
            return CompletedProcess(command, 0, "pg_dump (PostgreSQL) 18.6", "")
        if self.fail_command and Path(command[0]).name == self.fail_command:
            return CompletedProcess(command, 1, "", "sensitive database error")
        if Path(command[0]).name == "pg_dump":
            output = next(item.split("=", 1)[1] for item in command if item.startswith("--file="))
            Path(output).write_bytes(b"synthetic-postgresql-archive")
        return CompletedProcess(command, 0, "ok", "")


def test_backup_uses_pg_environment_and_writes_verified_metadata(tmp_path: Path) -> None:
    runner = FakeRunner()
    archive = tmp_path / "crm.dump"

    metadata = create_backup(
        DATABASE_URL,
        archive,
        runner=runner,
        migration_revision="20261028_0009",
    )

    assert archive.read_bytes() == b"synthetic-postgresql-archive"
    stored = json.loads((tmp_path / "crm.dump.metadata.json").read_text(encoding="utf-8"))
    assert stored == metadata
    assert stored["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert stored["migration_revision"] == "20261028_0009"
    assert all("top-secret" not in " ".join(command) for command, _ in runner.calls)
    assert all(environment["PGPASSWORD"] == "top-secret" for _, environment in runner.calls)


def test_backup_failure_never_reports_or_leaves_successful_archive(tmp_path: Path) -> None:
    archive = tmp_path / "crm.dump"

    with pytest.raises(BackupError, match="pg_dump failed") as failure:
        create_backup(
            DATABASE_URL,
            archive,
            runner=FakeRunner(fail_command="pg_dump"),
            migration_revision="head",
        )

    assert "sensitive database error" not in str(failure.value)
    assert not archive.exists()
    assert not (tmp_path / "crm.dump.metadata.json").exists()


def test_restore_requires_checksum_empty_disposable_target_and_confirmation(tmp_path: Path) -> None:
    runner = FakeRunner()
    archive = tmp_path / "crm.dump"
    create_backup(DATABASE_URL, archive, runner=runner, migration_revision="head")

    with pytest.raises(BackupError, match="explicit confirmation"):
        restore_backup(DATABASE_URL, archive, environment="test", confirmed=False, runner=runner)
    with pytest.raises(BackupError, match="production restore is prohibited"):
        restore_backup(
            DATABASE_URL, archive, environment="production", confirmed=True, runner=runner
        )
    with pytest.raises(BackupError, match="disposable"):
        restore_backup(
            "postgresql+psycopg://crm:secret@db.internal/kuratorskaya",
            archive,
            environment="test",
            confirmed=True,
            runner=runner,
        )

    archive.write_bytes(b"corrupt")
    with pytest.raises(BackupError, match="checksum"):
        restore_backup(DATABASE_URL, archive, environment="test", confirmed=True, runner=runner)


def test_verified_backup_restores_to_empty_disposable_database(tmp_path: Path) -> None:
    runner = FakeRunner()
    archive = tmp_path / "crm.dump"
    create_backup(DATABASE_URL, archive, runner=runner, migration_revision="head")

    restore_backup(
        DATABASE_URL,
        archive,
        environment="test",
        confirmed=True,
        runner=runner,
        target_is_empty=lambda _: True,
        revision_reader=lambda _: "head",
    )

    restore_commands = [command for command, _ in runner.calls if command[0] == "pg_restore"]
    assert any(
        "--exit-on-error" in command and "--single-transaction" in command
        for command in restore_commands
    )
    assert any("--dbname=kuratorskaya_test" in command for command in restore_commands)
    assert all("top-secret" not in " ".join(command) for command in restore_commands)


def test_existing_backup_is_not_overwritten(tmp_path: Path) -> None:
    archive = tmp_path / "crm.dump"
    archive.write_bytes(b"keep-me")

    with pytest.raises(BackupError, match="already exists"):
        create_backup(
            DATABASE_URL,
            archive,
            runner=FakeRunner(),
            migration_revision="head",
        )

    assert archive.read_bytes() == b"keep-me"


def test_concurrent_backup_to_same_path_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "crm.dump"
    lock = tmp_path / ".crm.dump.lock"
    lock.write_text("active", encoding="utf-8")

    with pytest.raises(BackupError, match="already being created"):
        create_backup(
            DATABASE_URL,
            archive,
            runner=FakeRunner(),
            migration_revision="head",
        )

    assert lock.read_text(encoding="utf-8") == "active"


def test_metadata_install_failure_removes_orphan_archive(tmp_path: Path, monkeypatch) -> None:
    archive = tmp_path / "crm.dump"
    original_replace = backup_module.os.replace

    def fail_metadata(source, destination) -> None:
        if str(destination).endswith(".metadata.json"):
            raise OSError("synthetic metadata failure")
        original_replace(source, destination)

    monkeypatch.setattr(backup_module.os, "replace", fail_metadata)

    with pytest.raises(OSError, match="metadata failure"):
        create_backup(
            DATABASE_URL,
            archive,
            runner=FakeRunner(),
            migration_revision="head",
        )

    assert not archive.exists()
    assert not (tmp_path / "crm.dump.metadata.json").exists()
