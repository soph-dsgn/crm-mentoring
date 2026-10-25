from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.api.errors import ApiError
from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine, get_db
from app.main import create_app
from app.modules.groups.models import Group, GroupStatus
from app.modules.strategies import service as strategy_service
from app.modules.strategies.models import (
    AnyaApproval,
    Strategy,
    StrategySection,
    StrategyTask,
    TaskHistory,
)
from app.modules.strategies.schemas import SectionReorder, StrategyCreate
from app.modules.strategies.service import create_strategy, reorder_sections
from app.modules.students.models import Student
from app.modules.users.models import User, UserRole

PASSWORD = "correct horse battery staple"


@pytest.fixture
def strategy_api(tmp_path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'strategies.db').as_posix()}"
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


def add_user(
    client: TestClient,
    factory: sessionmaker[Session],
    login: str,
    *,
    role: UserRole = UserRole.ADMIN,
    owner: bool = False,
) -> User:
    user = User(
        login=login,
        role=role,
        password_hash=client.app.state.password_manager.hash(PASSWORD),
        is_owner=owner,
        must_change_password=False,
    )
    with factory.begin() as database:
        database.add(user)
    return user


def add_group(factory: sessionmaker[Session], curator: User) -> Group:
    group = Group(
        curator_id=curator.id,
        curator_role=UserRole.ADMIN,
        name=f"Группа {curator.login}",
        starts_at=date(2026, 10, 1),
        status=GroupStatus.ACTIVE,
    )
    with factory.begin() as database:
        database.add(group)
    return group


def add_student(
    factory: sessionmaker[Session],
    group: Group,
    name: str,
    *,
    user: User | None = None,
) -> Student:
    student = Student(group_id=group.id, name=name, user_id=user.id if user else None)
    with factory.begin() as database:
        database.add(student)
    return student


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


def test_strategy_creation_is_unique_and_scoped(strategy_api) -> None:
    client, factory = strategy_api
    owner = add_user(client, factory, "owner", owner=True)
    curator = add_user(client, factory, "curator")
    foreign_curator = add_user(client, factory, "foreign")
    own_group = add_group(factory, curator)
    foreign_group = add_group(factory, foreign_curator)
    own_student = add_student(factory, own_group, "Своя ученица")
    foreign_student = add_student(factory, foreign_group, "Чужая ученица")

    curator_headers = authenticate(client, curator.login)
    missing_csrf = client.post(
        f"/api/v1/students/{own_student.id}/strategy",
        json={},
        headers={"Origin": "http://testserver"},
    )
    wrong_origin_headers = {**curator_headers, "Origin": "https://attacker.example"}
    wrong_origin = client.post(
        f"/api/v1/students/{own_student.id}/strategy",
        json={},
        headers=wrong_origin_headers,
    )
    created = client.post(
        f"/api/v1/students/{own_student.id}/strategy",
        json={"source_metadata": {"source": "notion", "external_id": "abc"}},
        headers=curator_headers,
    )
    duplicate = client.post(
        f"/api/v1/students/{own_student.id}/strategy",
        json={},
        headers=curator_headers,
    )
    foreign = client.post(
        f"/api/v1/students/{foreign_student.id}/strategy",
        json={},
        headers=curator_headers,
    )
    mass_assignment = client.post(
        f"/api/v1/students/{own_student.id}/strategy",
        json={"student_id": foreign_student.id},
        headers=authenticate(client, owner.login),
    )

    assert missing_csrf.status_code == 403
    assert wrong_origin.status_code == 403
    assert created.status_code == 201, created.text
    assert created.json()["student_id"] == own_student.id
    assert created.json()["source_metadata"]["external_id"] == "abc"
    assert duplicate.status_code == 409
    assert foreign.status_code == 403
    assert mass_assignment.status_code == 422
    with factory() as database:
        assert len(list(database.scalars(select(Strategy)))) == 1


def test_student_reads_only_own_strategy(strategy_api) -> None:
    client, factory = strategy_api
    owner = add_user(client, factory, "owner", owner=True)
    first_user = add_user(client, factory, "first-student", role=UserRole.STUDENT)
    second_user = add_user(client, factory, "second-student", role=UserRole.STUDENT)
    group = add_group(factory, owner)
    first = add_student(factory, group, "Первая", user=first_user)
    second = add_student(factory, group, "Вторая", user=second_user)
    owner_headers = authenticate(client, owner.login)
    for student in (first, second):
        response = client.post(
            f"/api/v1/students/{student.id}/strategy", json={}, headers=owner_headers
        )
        assert response.status_code == 201

    student_headers = authenticate(client, first_user.login)
    assert (
        client.get(f"/api/v1/students/{first.id}/strategy", headers=student_headers).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/students/{second.id}/strategy", headers=student_headers).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/students/{first.id}/strategy", json={}, headers=student_headers
        ).status_code
        == 403
    )


def test_concurrent_strategy_creation_allows_exactly_one_writer(strategy_api) -> None:
    client, factory = strategy_api
    curator = add_user(client, factory, "curator")
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица")
    second_client = TestClient(client.app)
    first_headers = authenticate(client, curator.login)
    second_headers = authenticate(second_client, curator.login)
    barrier = Barrier(2)

    def create(test_client: TestClient, headers: dict[str, str]) -> int:
        barrier.wait()
        return test_client.post(
            f"/api/v1/students/{student.id}/strategy", json={}, headers=headers
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(create, client, first_headers),
                executor.submit(create, second_client, second_headers),
            ]
            statuses = [future.result() for future in futures]
    finally:
        second_client.close()

    assert sorted(statuses) == [201, 409]
    with factory() as database:
        assert len(list(database.scalars(select(Strategy)))) == 1


def create_strategy_section_task(
    client: TestClient,
    headers: dict[str, str],
    student: Student,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    strategy = client.post(
        f"/api/v1/students/{student.id}/strategy", json={}, headers=headers
    ).json()
    section = client.post(
        f"/api/v1/strategies/{strategy['id']}/sections",
        json={"title": "Портфолио", "position": 0},
        headers=headers,
    ).json()
    task = client.post(
        f"/api/v1/strategy-sections/{section['id']}/tasks",
        json={
            "title": "Собрать кейс",
            "description": "Описание",
            "materials": ["Бриф"],
            "links": {"figma": "https://figma.com/file"},
            "period_text": "Неделя 1",
            "position": 0,
        },
        headers=headers,
    ).json()
    return strategy, section, task


def test_sections_are_ordered_reordered_and_versioned(strategy_api) -> None:
    client, factory = strategy_api
    curator = add_user(client, factory, "curator")
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица")
    headers = authenticate(client, curator.login)
    strategy = client.post(
        f"/api/v1/students/{student.id}/strategy", json={}, headers=headers
    ).json()
    first = client.post(
        f"/api/v1/strategies/{strategy['id']}/sections",
        json={"title": "Первый", "position": 0},
        headers=headers,
    ).json()
    second = client.post(
        f"/api/v1/strategies/{strategy['id']}/sections",
        json={"title": "Второй", "position": 1},
        headers=headers,
    ).json()

    invalid = client.post(
        f"/api/v1/strategies/{strategy['id']}/sections/reorder",
        json={"items": [{"id": first["id"], "expected_version": 1, "position": 0}]},
        headers=headers,
    )
    reordered = client.post(
        f"/api/v1/strategies/{strategy['id']}/sections/reorder",
        json={
            "items": [
                {"id": first["id"], "expected_version": 1, "position": 1},
                {"id": second["id"], "expected_version": 1, "position": 0},
            ]
        },
        headers=headers,
    )
    stale = client.patch(
        f"/api/v1/strategy-sections/{first['id']}",
        json={"expected_version": 1, "title": "Устаревшее"},
        headers=headers,
    )

    assert invalid.status_code == 422
    assert reordered.status_code == 200
    assert [(item["title"], item["version"]) for item in reordered.json()] == [
        ("Второй", 2),
        ("Первый", 2),
    ]
    assert stale.status_code == 409


def test_task_lifecycle_history_and_mass_assignment(strategy_api) -> None:
    client, factory = strategy_api
    curator = add_user(client, factory, "curator")
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица")
    headers = authenticate(client, curator.login)
    _, section, task = create_strategy_section_task(client, headers, student)
    position_conflict = client.post(
        f"/api/v1/strategy-sections/{section['id']}/tasks",
        json={"title": "Конфликт", "position": 0},
        headers=headers,
    )

    invalid_jump = client.post(
        f"/api/v1/strategy-tasks/{task['id']}/study-status",
        json={"expected_version": 1, "study_status": "done"},
        headers=headers,
    )
    started = client.post(
        f"/api/v1/strategy-tasks/{task['id']}/study-status",
        json={"expected_version": 1, "study_status": "in_progress"},
        headers=headers,
    )
    mass_assignment = client.patch(
        f"/api/v1/strategy-tasks/{task['id']}",
        json={
            "expected_version": 2,
            "strategy_id": "foreign",
            "position": 9,
            "title": "Подмена",
        },
        headers=headers,
    )
    archived = client.post(
        f"/api/v1/strategy-tasks/{task['id']}/archive",
        json={"expected_version": 2},
        headers=headers,
    )
    edit_archived = client.patch(
        f"/api/v1/strategy-tasks/{task['id']}",
        json={"expected_version": 3, "title": "Нельзя"},
        headers=headers,
    )
    restored = client.post(
        f"/api/v1/strategy-tasks/{task['id']}/restore",
        json={"expected_version": 3},
        headers=headers,
    )
    history = client.get(f"/api/v1/strategy-tasks/{task['id']}/history", headers=headers)

    assert invalid_jump.status_code == 409
    assert position_conflict.status_code == 409
    assert started.status_code == 200
    assert mass_assignment.status_code == 422
    assert archived.status_code == 200 and archived.json()["archived_at"] is not None
    assert edit_archived.status_code == 409
    assert restored.status_code == 200 and restored.json()["archived_at"] is None
    assert [item["event_type"] for item in history.json()["items"]] == [
        "task_created",
        "study_status_changed",
        "task_archived",
        "task_restored",
    ]
    with factory() as database:
        assert database.get(StrategyTask, task["id"]) is not None


def test_approval_resubmission_recall_and_history(strategy_api) -> None:
    client, factory = strategy_api
    curator = add_user(client, factory, "curator")
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица")
    headers = authenticate(client, curator.login)
    _, _, task = create_strategy_section_task(client, headers, student)

    created = client.post(
        f"/api/v1/strategy-tasks/{task['id']}/approval",
        json={"comment": "Передать"},
        headers=headers,
    )
    duplicate = client.post(
        f"/api/v1/strategy-tasks/{task['id']}/approval", json={}, headers=headers
    )
    sent = client.post(
        f"/api/v1/strategy-tasks/{task['id']}/approval/transition",
        json={"expected_version": 1, "status": "sent"},
        headers=headers,
    )
    stale = client.post(
        f"/api/v1/strategy-tasks/{task['id']}/approval/transition",
        json={"expected_version": 1, "status": "reviewing"},
        headers=headers,
    )
    reviewing = client.post(
        f"/api/v1/strategy-tasks/{task['id']}/approval/transition",
        json={"expected_version": 2, "status": "reviewing"},
        headers=headers,
    )
    revision = client.post(
        f"/api/v1/strategy-tasks/{task['id']}/approval/transition",
        json={"expected_version": 3, "status": "revision", "comment": "Есть правки"},
        headers=headers,
    )
    resent = client.post(
        f"/api/v1/strategy-tasks/{task['id']}/approval/transition",
        json={"expected_version": 4, "status": "sent"},
        headers=headers,
    )
    recalled = client.post(
        f"/api/v1/strategy-tasks/{task['id']}/approval/transition",
        json={"expected_version": 5, "status": "to_send"},
        headers=headers,
    )

    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert stale.status_code == 409
    assert [response.status_code for response in (sent, reviewing, revision, resent, recalled)] == [
        200,
        200,
        200,
        200,
        200,
    ]
    assert recalled.json()["status"] == "to_send"
    assert recalled.json()["comment"] == "Есть правки"
    with factory() as database:
        assert database.scalar(select(AnyaApproval).where(AnyaApproval.task_id == task["id"]))
        history = list(
            database.scalars(select(TaskHistory).where(TaskHistory.task_id == task["id"]))
        )
        assert len(history) == 7


def test_curator_reassignment_blocks_stale_mutation(strategy_api) -> None:
    client, factory = strategy_api
    old_curator = add_user(client, factory, "old")
    new_curator = add_user(client, factory, "new")
    group = add_group(factory, old_curator)
    student = add_student(factory, group, "Ученица")
    headers = authenticate(client, old_curator.login)
    _, _, task = create_strategy_section_task(client, headers, student)
    with factory.begin() as database:
        database.execute(
            update(Group)
            .where(Group.id == group.id)
            .values(curator_id=new_curator.id, version=Group.version + 1)
        )

    response = client.patch(
        f"/api/v1/strategy-tasks/{task['id']}",
        json={"expected_version": 1, "title": "Подмена после переназначения"},
        headers=headers,
    )

    assert response.status_code == 403
    with factory() as database:
        assert database.get(StrategyTask, task["id"]).title == "Собрать кейс"


def test_stale_curator_cannot_create_strategy_after_reassignment(strategy_api) -> None:
    _, factory = strategy_api
    with factory.begin() as setup:
        old_curator = User(
            login="old-direct",
            role=UserRole.ADMIN,
            password_hash="hash",
            must_change_password=False,
        )
        new_curator = User(
            login="new-direct",
            role=UserRole.ADMIN,
            password_hash="hash",
            must_change_password=False,
        )
        setup.add_all([old_curator, new_curator])
        setup.flush()
        group = Group(
            curator_id=old_curator.id,
            curator_role=UserRole.ADMIN,
            name="Группа",
            starts_at=date(2026, 10, 1),
        )
        setup.add(group)
        setup.flush()
        student = Student(group_id=group.id, name="Ученица")
        setup.add(student)
    first = factory()
    try:
        stale_actor = first.get(User, old_curator.id)
        stale_student = first.get(Student, student.id)
        with factory.begin() as concurrent:
            concurrent.execute(
                update(Group)
                .where(Group.id == group.id)
                .values(curator_id=new_curator.id, version=Group.version + 1)
            )

        with pytest.raises(ApiError) as error:
            create_strategy(first, stale_actor, stale_student, StrategyCreate())
        assert getattr(error.value, "code", None) == "curator_assignment_changed"
        first.rollback()
    finally:
        first.close()
    with factory() as database:
        assert database.scalar(select(Strategy)) is None


def test_task_list_reorder_and_stale_version(strategy_api) -> None:
    client, factory = strategy_api
    curator = add_user(client, factory, "curator")
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица")
    headers = authenticate(client, curator.login)
    _, section, first = create_strategy_section_task(client, headers, student)
    second = client.post(
        f"/api/v1/strategy-sections/{section['id']}/tasks",
        json={"title": "Вторая", "position": 1},
        headers=headers,
    ).json()

    reordered = client.post(
        f"/api/v1/strategy-sections/{section['id']}/tasks/reorder",
        json={
            "items": [
                {"id": first["id"], "expected_version": 1, "position": 1},
                {"id": second["id"], "expected_version": 1, "position": 0},
            ]
        },
        headers=headers,
    )
    stale = client.post(
        f"/api/v1/strategy-sections/{section['id']}/tasks/reorder",
        json={
            "items": [
                {"id": first["id"], "expected_version": 1, "position": 0},
                {"id": second["id"], "expected_version": 1, "position": 1},
            ]
        },
        headers=headers,
    )
    listing = client.get(f"/api/v1/strategy-sections/{section['id']}/tasks", headers=headers)

    assert [(item["title"], item["version"]) for item in reordered.json()] == [
        ("Вторая", 2),
        ("Собрать кейс", 2),
    ]
    assert stale.status_code == 409
    assert [item["id"] for item in listing.json()] == [second["id"], first["id"]]


def test_section_reorder_revalidates_complete_set_after_lock(strategy_api, monkeypatch) -> None:
    client, factory = strategy_api
    curator = add_user(client, factory, "curator")
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица")
    headers = authenticate(client, curator.login)
    strategy = client.post(
        f"/api/v1/students/{student.id}/strategy", json={}, headers=headers
    ).json()
    sections = [
        client.post(
            f"/api/v1/strategies/{strategy['id']}/sections",
            json={"title": title, "position": position},
            headers=headers,
        ).json()
        for position, title in enumerate(("Первый", "Второй"))
    ]
    payload = SectionReorder(
        items=[
            {"id": sections[0]["id"], "expected_version": 1, "position": 1},
            {"id": sections[1]["id"], "expected_version": 1, "position": 0},
        ]
    )
    original_lock = strategy_service._lock_strategy_write

    def insert_before_lock(database, loaded_strategy, actor) -> None:
        database.add(
            StrategySection(
                strategy_id=loaded_strategy.id,
                title="Конкурентный раздел",
                position=2,
            )
        )
        database.flush()
        original_lock(database, loaded_strategy, actor)

    monkeypatch.setattr(strategy_service, "_lock_strategy_write", insert_before_lock)
    with factory() as database:
        actor = database.get(User, curator.id)
        loaded_strategy = database.get(Strategy, strategy["id"])
        with pytest.raises(ApiError) as error:
            reorder_sections(
                database,
                actor,
                loaded_strategy,
                payload,
                datetime.now(UTC),
            )
        assert error.value.code == "invalid_reorder"
        database.rollback()


def test_concurrent_task_reorder_allows_exactly_one_writer(strategy_api) -> None:
    client, factory = strategy_api
    curator = add_user(client, factory, "curator")
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица")
    first_headers = authenticate(client, curator.login)
    _, section, first = create_strategy_section_task(client, first_headers, student)
    second = client.post(
        f"/api/v1/strategy-sections/{section['id']}/tasks",
        json={"title": "Вторая", "position": 1},
        headers=first_headers,
    ).json()
    second_client = TestClient(client.app)
    second_headers = authenticate(second_client, curator.login)
    barrier = Barrier(2)

    def reorder(test_client: TestClient, headers: dict[str, str], reverse: bool) -> int:
        positions = (1, 0) if reverse else (0, 1)
        barrier.wait()
        return test_client.post(
            f"/api/v1/strategy-sections/{section['id']}/tasks/reorder",
            json={
                "items": [
                    {"id": first["id"], "expected_version": 1, "position": positions[0]},
                    {"id": second["id"], "expected_version": 1, "position": positions[1]},
                ]
            },
            headers=headers,
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(reorder, client, first_headers, False),
                executor.submit(reorder, second_client, second_headers, True),
            ]
            statuses = [future.result() for future in futures]
    finally:
        second_client.close()

    assert sorted(statuses) == [200, 409]
    with factory() as database:
        persisted = list(
            database.scalars(
                select(StrategyTask)
                .where(StrategyTask.section_id == section["id"])
                .order_by(StrategyTask.position)
            )
        )
        assert [task.position for task in persisted] == [0, 1]
        assert [task.version for task in persisted] == [2, 2]


def test_section_task_updates_and_history_cursor(strategy_api) -> None:
    client, factory = strategy_api
    curator = add_user(client, factory, "curator")
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица")
    headers = authenticate(client, curator.login)
    _, section, task = create_strategy_section_task(client, headers, student)

    section_response = client.patch(
        f"/api/v1/strategy-sections/{section['id']}",
        json={"expected_version": 1, "title": "Новое название"},
        headers=headers,
    )
    task_response = client.patch(
        f"/api/v1/strategy-tasks/{task['id']}",
        json={
            "expected_version": 1,
            "title": "Обновлённая задача",
            "links": {"notion": "https://notion.so/page"},
            "due_at": "2026-11-01T12:00:00Z",
        },
        headers=headers,
    )
    first_page = client.get(f"/api/v1/strategy-tasks/{task['id']}/history?limit=1", headers=headers)
    cursor = first_page.json()["next_cursor"]
    second_page = client.get(
        f"/api/v1/strategy-tasks/{task['id']}/history?limit=1&cursor={cursor}",
        headers=headers,
    )
    invalid_cursor = client.get(
        f"/api/v1/strategy-tasks/{task['id']}/history?cursor=not-base64!",
        headers=headers,
    )

    assert section_response.status_code == 200
    assert section_response.json()["version"] == 2
    assert task_response.status_code == 200
    assert task_response.json()["version"] == 2
    assert task_response.json()["links"] == {"notion": "https://notion.so/page"}
    assert first_page.json()["items"][0]["event_type"] == "task_created"
    assert second_page.json()["items"][0]["event_type"] == "task_updated"
    assert invalid_cursor.status_code == 422


def test_concurrent_task_patch_allows_exactly_one_writer(strategy_api) -> None:
    client, factory = strategy_api
    curator = add_user(client, factory, "curator")
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица")
    first_headers = authenticate(client, curator.login)
    _, _, task = create_strategy_section_task(client, first_headers, student)
    second_client = TestClient(client.app)
    second_headers = authenticate(second_client, curator.login)
    barrier = Barrier(2)

    def patch(test_client: TestClient, headers: dict[str, str], title: str) -> int:
        barrier.wait()
        return test_client.patch(
            f"/api/v1/strategy-tasks/{task['id']}",
            json={"expected_version": 1, "title": title},
            headers=headers,
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(patch, client, first_headers, "Первая запись"),
                executor.submit(patch, second_client, second_headers, "Вторая запись"),
            ]
            statuses = [future.result() for future in futures]
    finally:
        second_client.close()

    assert sorted(statuses) == [200, 409]
    with factory() as database:
        persisted = database.get(StrategyTask, task["id"])
        assert persisted.version == 2
        assert persisted.title in {"Первая запись", "Вторая запись"}


def test_read_access_and_mutation_boundaries(strategy_api) -> None:
    client, factory = strategy_api
    owner = add_user(client, factory, "owner", owner=True)
    curator = add_user(client, factory, "curator")
    reader = add_user(client, factory, "reader")
    student_user = add_user(client, factory, "student", role=UserRole.STUDENT)
    foreign_student_user = add_user(client, factory, "foreign-student", role=UserRole.STUDENT)
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица", user=student_user)
    foreign_student = add_student(factory, group, "Чужая", user=foreign_student_user)
    headers = authenticate(client, curator.login)
    strategy, section, task = create_strategy_section_task(client, headers, student)
    foreign_strategy = client.post(
        f"/api/v1/students/{foreign_student.id}/strategy",
        json={},
        headers=authenticate(client, owner.login),
    ).json()
    with factory.begin() as database:
        database.execute(
            update(Group).where(Group.id == group.id).values(status=GroupStatus.ARCHIVED)
        )

    reader_headers = authenticate(client, reader.login)
    assert (
        client.get(f"/api/v1/strategy-tasks/{task['id']}", headers=reader_headers).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/strategy-tasks/{task['id']}",
            json={"expected_version": 1, "title": "Чужое изменение"},
            headers=reader_headers,
        ).status_code
        == 403
    )

    student_headers = authenticate(client, student_user.login)
    assert (
        client.get(f"/api/v1/students/{student.id}/strategy", headers=student_headers).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/strategies/{strategy['id']}/sections", headers=student_headers
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/strategy-sections/{section['id']}/tasks", headers=student_headers
        ).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/strategy-tasks/{task['id']}", headers=student_headers).status_code
        == 200
    )
    student_history = client.get(
        f"/api/v1/strategy-tasks/{task['id']}/history", headers=student_headers
    )
    assert student_history.status_code == 200
    assert "actor_user_id" not in student_history.json()["items"][0]
    assert (
        client.get(
            f"/api/v1/strategies/{foreign_strategy['id']}/sections", headers=student_headers
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/strategy-tasks/{task['id']}",
            json={"expected_version": 1, "title": "Нельзя"},
            headers=student_headers,
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/v1/students/missing/strategy", None),
        ("post", "/api/v1/students/missing/strategy", {}),
        ("get", "/api/v1/strategies/missing/sections", None),
        ("post", "/api/v1/strategies/missing/sections", {"title": "X", "position": 0}),
        ("get", "/api/v1/strategy-sections/missing/tasks", None),
        ("get", "/api/v1/strategy-tasks/missing", None),
        ("get", "/api/v1/strategy-tasks/missing/history", None),
        ("get", "/api/v1/strategy-tasks/missing/approval", None),
    ],
)
def test_strategy_routes_require_authentication(strategy_api, method, path, payload) -> None:
    client, _ = strategy_api
    response = client.request(method, path, json=payload)
    assert response.status_code == 401
