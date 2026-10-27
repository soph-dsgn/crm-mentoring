from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine, get_db
from app.main import create_app
from app.modules.groups.models import Group, GroupStatus
from app.modules.homeworks.models import HomeworkItem
from app.modules.legacy_io.models import ImportRun, LegacyIdMapping
from app.modules.legacy_io.service import restore_backup
from app.modules.strategies.models import Strategy, StrategyTask
from app.modules.students.models import Student
from app.modules.users.models import User, UserRole

PASSWORD = "correct horse battery staple"


@pytest.fixture
def import_api(tmp_path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'legacy-import.db').as_posix()}"
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        environment="test",
        database_url=database_url,
        auth_argon2_time_cost=1,
        auth_argon2_memory_cost=1024,
        auth_argon2_parallelism=1,
        _env_file=None,
    )
    application = create_app(settings)

    def override_db() -> Iterator[Session]:
        with factory() as database:
            yield database

    application.dependency_overrides[get_db] = override_db
    with TestClient(application) as client:
        yield client, factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def add_user(client, factory, login: str, *, owner=False, role=UserRole.ADMIN) -> User:
    user = User(
        login=login,
        role=role,
        password_hash=client.app.state.password_manager.hash(PASSWORD),
        is_owner=owner,
        is_active=True,
        must_change_password=False,
    )
    with factory.begin() as database:
        database.add(user)
    return user


def authenticate(client: TestClient, login: str) -> dict[str, str]:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        json={"login": login, "password": PASSWORD},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200
    return {
        "Origin": "http://testserver",
        "X-CSRF-Token": client.cookies.get("kuratorskaya_csrf"),
    }


def source() -> dict[str, object]:
    return {
        "version": 3,
        "demo": False,
        "groups": [
            {
                "id": "legacy-group",
                "name": "Тестовая группа",
                "startsAt": "2026-01-10",
                "endsAt": "2026-05-10",
                "actualEndsAt": "",
                "status": "active",
                "statusBeforeArchive": None,
                "notes": "",
                "createdAt": "2026-01-01T00:00:00Z",
            }
        ],
        "students": [
            {
                "id": "legacy-student",
                "groupId": "legacy-group",
                "name": "Тестовая ученица",
                "stage": "start",
                "links": {"figma": "https://example.test/design"},
                "createdAt": "2026-01-02T00:00:00Z",
            }
        ],
        "sections": [
            {
                "id": "legacy-section",
                "studentId": "legacy-student",
                "title": "Начало",
                "order": 0,
                "createdAt": "2026-01-03T00:00:00Z",
            }
        ],
        "tasks": [
            {
                "id": "legacy-task",
                "studentId": "legacy-student",
                "sectionId": "legacy-section",
                "title": "Тестовая задача",
                "description": "Описание",
                "status": "progress",
                "studyStatus": "in_progress",
                "reviewStatus": "revision",
                "approvalStatus": "sent",
                "approvalComment": "Комментарий",
                "order": 0,
                "materials": ["https://example.test/material"],
                "history": [{"at": "2026-01-04T00:00:00Z", "label": "Legacy"}],
                "createdAt": "2026-01-03T00:00:00Z",
                "updatedAt": "2026-01-04T00:00:00Z",
            }
        ],
        "meetings": [
            {
                "id": "legacy-meeting",
                "studentId": "legacy-student",
                "date": "2026-01-15",
                "title": "Встреча",
                "summary": "Итог",
                "createdAt": "2026-01-15T12:00:00Z",
            }
        ],
        "homeworks": [
            {
                "id": "legacy-homework",
                "studentId": "legacy-student",
                "title": "Домашняя работа",
                "text": "Текст",
                "status": "revision",
                "issuedAt": "2026-01-16T00:00:00Z",
                "submittedAt": "2026-01-17T00:00:00Z",
                "workUrl": "https://example.test/work",
                "comment": "Доработать",
                "dueAt": "2026-01-20",
                "createdAt": "2026-01-16T00:00:00Z",
                "items": [
                    {
                        "taskId": "legacy-task",
                        "title": "Снимок задачи",
                        "description": "Снимок описания",
                        "url": "https://example.test/task",
                        "materials": ["https://example.test/snapshot"],
                        "dueAt": "2026-01-20",
                    }
                ],
            }
        ],
    }


def request_body(curator_id: str) -> dict[str, object]:
    return {"source": source(), "curator_assignments": {"legacy-group": curator_id}}


def test_validate_is_owner_only_and_writes_nothing(import_api) -> None:
    client, factory = import_api
    owner = add_user(client, factory, "owner", owner=True)
    admin = add_user(client, factory, "admin")

    headers = authenticate(client, admin.login)
    assert (
        client.post(
            "/api/v1/imports/legacy/validate", json=request_body(admin.id), headers=headers
        ).status_code
        == 403
    )

    headers = authenticate(client, owner.login)
    response = client.post(
        "/api/v1/imports/legacy/validate", json=request_body(admin.id), headers=headers
    )
    assert response.status_code == 200
    report = response.json()
    assert report["valid"] is True
    assert report["counts"] == {
        "groups": 1,
        "students": 1,
        "strategies": 1,
        "sections": 1,
        "tasks": 1,
        "meetings": 1,
        "homeworks": 1,
        "homework_items": 1,
        "approvals": 1,
    }
    assert report["checksum"]
    assert "legacy task history has no actor" in " ".join(report["warnings"]).lower()
    with factory() as database:
        assert database.scalar(select(func.count(ImportRun.id))) == 0
        assert database.scalar(select(func.count(LegacyIdMapping.id))) == 0


def test_import_is_atomic_idempotent_and_preserves_snapshots(import_api) -> None:
    client, factory = import_api
    owner = add_user(client, factory, "owner", owner=True)
    headers = authenticate(client, owner.login)
    preview = client.post(
        "/api/v1/imports/legacy/validate", json=request_body(owner.id), headers=headers
    )
    checksum = preview.json()["checksum"]
    payload = {**request_body(owner.id), "confirmation_checksum": checksum, "confirm": True}

    first = client.post("/api/v1/imports/legacy", json=payload, headers=headers)
    second = client.post("/api/v1/imports/legacy", json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["import_run_id"] == first.json()["import_run_id"]
    assert second.json()["idempotent_replay"] is True
    with factory() as database:
        assert database.scalar(select(func.count(Group.id))) == 1
        assert database.scalar(select(func.count(Student.id))) == 1
        assert database.scalar(select(func.count(ImportRun.id))) == 1
        assert database.scalar(select(func.count(LegacyIdMapping.id))) == 7
        snapshot = database.scalar(select(HomeworkItem))
        task = database.scalar(select(StrategyTask))
        strategy = database.scalar(select(Strategy))
        assert snapshot.title == "Снимок задачи"
        assert snapshot.description == "Снимок описания"
        assert task.title == "Тестовая задача"
        assert strategy.source_metadata["legacy_tasks"]["legacy-task"]["history"]


def test_validation_rejects_orphans_duplicates_and_existing_data(import_api) -> None:
    client, factory = import_api
    owner = add_user(client, factory, "owner", owner=True)
    headers = authenticate(client, owner.login)
    invalid = source()
    invalid["tasks"] = [invalid["tasks"][0], invalid["tasks"][0]]
    invalid["meetings"][0]["studentId"] = "missing"
    response = client.post(
        "/api/v1/imports/legacy/validate",
        json={"source": invalid, "curator_assignments": {"legacy-group": owner.id}},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert {item["code"] for item in response.json()["conflicts"]} >= {
        "duplicate_id",
        "orphan_reference",
    }

    with factory.begin() as database:
        database.add(
            Group(
                curator_id=owner.id,
                curator_role=UserRole.ADMIN,
                name="Existing",
                starts_at=date(2026, 1, 1),
                status=GroupStatus.ACTIVE,
            )
        )
    response = client.post(
        "/api/v1/imports/legacy/validate", json=request_body(owner.id), headers=headers
    )
    assert response.json()["valid"] is False
    assert "server_data_conflict" in {item["code"] for item in response.json()["conflicts"]}


def test_export_is_owner_only_and_excludes_auth_secrets(import_api) -> None:
    client, factory = import_api
    owner = add_user(client, factory, "owner", owner=True)
    student = add_user(client, factory, "student", role=UserRole.STUDENT)
    assert (
        client.get(
            "/api/v1/exports/backup", headers=authenticate(client, student.login)
        ).status_code
        == 403
    )

    response = client.get("/api/v1/exports/backup", headers=authenticate(client, owner.login))
    assert response.status_code == 200
    body = response.json()
    assert body["schema"] == "kuratorskaya-backup"
    assert body["version"] == 1
    serialized = response.text.lower()
    for secret in ("password_hash", "csrf", "session", PASSWORD.lower()):
        assert secret not in serialized


def test_import_requires_csrf_confirmation_and_matching_checksum(import_api) -> None:
    client, factory = import_api
    owner = add_user(client, factory, "owner", owner=True)
    headers = authenticate(client, owner.login)
    body = request_body(owner.id)
    assert client.post("/api/v1/imports/legacy/validate", json=body).status_code == 403
    assert (
        client.post(
            "/api/v1/imports/legacy",
            json={**body, "confirm": True, "confirmation_checksum": "0" * 64},
            headers=headers,
        ).status_code
        == 409
    )


def test_supported_v1_builds_deterministic_section_and_rejects_invalid_status(import_api) -> None:
    client, factory = import_api
    owner = add_user(client, factory, "owner", owner=True)
    headers = authenticate(client, owner.login)
    legacy = source()
    legacy["version"] = 1
    legacy.pop("sections")
    legacy["tasks"][0]["sectionId"] = ""
    response = client.post(
        "/api/v1/imports/legacy/validate",
        json={"source": legacy, "curator_assignments": {"legacy-group": owner.id}},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True

    legacy["tasks"][0]["studyStatus"] = "unknown"
    response = client.post(
        "/api/v1/imports/legacy/validate",
        json={"source": legacy, "curator_assignments": {"legacy-group": owner.id}},
        headers=headers,
    )
    assert response.json()["valid"] is False
    assert "invalid_task_status" in {item["code"] for item in response.json()["conflicts"]}


def test_malformed_oversized_and_extra_fields_are_rejected(import_api) -> None:
    client, factory = import_api
    owner = add_user(client, factory, "owner", owner=True)
    headers = authenticate(client, owner.login)
    malformed = client.post(
        "/api/v1/imports/legacy/validate",
        content=b"{",
        headers={**headers, "Content-Type": "application/json"},
    )
    assert malformed.status_code == 422
    oversized = client.post(
        "/api/v1/imports/legacy/validate",
        content=b"{}",
        headers={**headers, "Content-Type": "application/json", "Content-Length": "6000000"},
    )
    assert oversized.status_code == 413
    extra = request_body(owner.id)
    extra["unexpected"] = True
    assert (
        client.post("/api/v1/imports/legacy/validate", json=extra, headers=headers).status_code
        == 422
    )
    operation = client.get("/openapi.json").json()["paths"]["/api/v1/imports/legacy/validate"][
        "post"
    ]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["title"] == (
        "LegacyImportRequest"
    )


def test_export_restores_round_trip_into_isolated_database(import_api, tmp_path) -> None:
    client, factory = import_api
    owner = add_user(client, factory, "owner", owner=True)
    headers = authenticate(client, owner.login)
    preview = client.post(
        "/api/v1/imports/legacy/validate", json=request_body(owner.id), headers=headers
    ).json()
    imported = client.post(
        "/api/v1/imports/legacy",
        json={
            **request_body(owner.id),
            "confirm": True,
            "confirmation_checksum": preview["checksum"],
        },
        headers=headers,
    )
    assert imported.status_code == 201
    backup = client.get("/api/v1/exports/backup", headers=headers).json()

    target_engine = build_engine(f"sqlite+pysqlite:///{(tmp_path / 'round-trip.db').as_posix()}")
    Base.metadata.create_all(target_engine)
    target_factory = sessionmaker(bind=target_engine, expire_on_commit=False)
    with pytest.raises(ValueError, match="matching users"), target_factory.begin() as database:
        restore_backup(database, backup)
    with target_factory() as database:
        assert database.scalar(select(func.count(Group.id))) == 0
        assert database.scalar(select(func.count(ImportRun.id))) == 0
    with target_factory.begin() as database:
        database.add(
            User(
                id=owner.id,
                login="restore-owner",
                role=UserRole.ADMIN,
                password_hash="not-exported",
                is_owner=True,
                is_active=True,
                must_change_password=True,
            )
        )
    with target_factory.begin() as database:
        counts = restore_backup(database, backup)
        assert counts["groups"] == 1
        assert counts["homework_items"] == 1
    with target_factory() as database:
        assert database.scalar(select(HomeworkItem)).title == "Снимок задачи"
        assert database.scalar(select(func.count(LegacyIdMapping.id))) == 7
    Base.metadata.drop_all(target_engine)
    target_engine.dispose()


def test_concurrent_identical_import_is_idempotent(import_api) -> None:
    client, factory = import_api
    owner = add_user(client, factory, "owner", owner=True)
    headers = authenticate(client, owner.login)
    checksum = client.post(
        "/api/v1/imports/legacy/validate", json=request_body(owner.id), headers=headers
    ).json()["checksum"]
    payload = {
        **request_body(owner.id),
        "confirm": True,
        "confirmation_checksum": checksum,
    }

    def submit() -> tuple[int, str]:
        with TestClient(client.app) as worker:
            worker_headers = authenticate(worker, owner.login)
            response = worker.post("/api/v1/imports/legacy", json=payload, headers=worker_headers)
            return response.status_code, response.json()["import_run_id"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: submit(), range(2)))

    assert sorted(status_code for status_code, _ in results) == [200, 201]
    assert len({run_id for _, run_id in results}) == 1
    with factory() as database:
        assert database.scalar(select(func.count(ImportRun.id))) == 1
        assert database.scalar(select(func.count(Group.id))) == 1


def test_failure_after_writes_rolls_back_entities_and_import_run(import_api, monkeypatch) -> None:
    client, factory = import_api
    owner = add_user(client, factory, "owner", owner=True)
    headers = authenticate(client, owner.login)
    checksum = client.post(
        "/api/v1/imports/legacy/validate", json=request_body(owner.id), headers=headers
    ).json()["checksum"]

    def fail_audit(*args, **kwargs):
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr("app.modules.legacy_io.service.record_audit", fail_audit)
    with TestClient(client.app, raise_server_exceptions=False) as worker:
        worker_headers = authenticate(worker, owner.login)
        response = worker.post(
            "/api/v1/imports/legacy",
            json={
                **request_body(owner.id),
                "confirm": True,
                "confirmation_checksum": checksum,
            },
            headers=worker_headers,
        )
    assert response.status_code == 500
    with factory() as database:
        assert database.scalar(select(func.count(ImportRun.id))) == 0
        assert database.scalar(select(func.count(Group.id))) == 0


def test_same_name_students_are_not_merged_and_accounts_are_not_created(import_api) -> None:
    client, factory = import_api
    owner = add_user(client, factory, "owner", owner=True)
    headers = authenticate(client, owner.login)
    legacy = source()
    second_group = {**legacy["groups"][0], "id": "legacy-group-2", "name": "Вторая группа"}
    second_student = {
        **legacy["students"][0],
        "id": "legacy-student-2",
        "groupId": "legacy-group-2",
    }
    legacy["groups"].append(second_group)
    legacy["students"].append(second_student)
    body = {
        "source": legacy,
        "curator_assignments": {
            "legacy-group": owner.id,
            "legacy-group-2": owner.id,
        },
    }
    preview = client.post("/api/v1/imports/legacy/validate", json=body, headers=headers).json()
    response = client.post(
        "/api/v1/imports/legacy",
        json={**body, "confirm": True, "confirmation_checksum": preview["checksum"]},
        headers=headers,
    )
    assert response.status_code == 201
    with factory() as database:
        assert database.scalar(select(func.count(Student.id))) == 2
        assert database.scalar(select(func.count(User.id))) == 1
