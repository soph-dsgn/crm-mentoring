from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine, get_db
from app.main import create_app
from app.modules.groups.models import Group, GroupStatus
from app.modules.homeworks.models import Homework, HomeworkHistory, HomeworkItem, HomeworkStatus
from app.modules.strategies.models import (
    AnyaApproval,
    ApprovalStatus,
    Strategy,
    StrategySection,
    StrategyTask,
    StudyStatus,
    TaskHistory,
)
from app.modules.students.models import Student
from app.modules.users.audit import AuditAction, AuditEvent
from app.modules.users.models import User, UserRole

PASSWORD = "correct horse battery staple"


@pytest.fixture
def learning_api(tmp_path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'learning.db').as_posix()}"
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


def add_group(factory: sessionmaker[Session], curator: User, name: str = "Группа") -> Group:
    group = Group(
        curator_id=curator.id,
        curator_role=UserRole.ADMIN,
        name=name,
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


def add_strategy_task(factory: sessionmaker[Session], student: Student, title: str) -> StrategyTask:
    with factory.begin() as database:
        strategy = Strategy(student_id=student.id)
        database.add(strategy)
        database.flush()
        section = StrategySection(strategy_id=strategy.id, title="Раздел", position=0)
        database.add(section)
        database.flush()
        task = StrategyTask(
            strategy_id=strategy.id,
            section_id=section.id,
            title=title,
            description="Исходное описание",
            materials=["Материал"],
            links={"brief": "https://example.com/brief"},
            period_text="Неделя 1",
            position=0,
        )
        database.add(task)
    return task


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


def create_homework(
    client: TestClient,
    headers: dict[str, str],
    task: StrategyTask,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/strategies/{task.strategy_id}/homeworks",
        json={
            "title": "Домашнее задание",
            "description": "Собрать и отправить работу",
            "task_ids": [task.id],
            "links": {"notion": "https://example.com/homework"},
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def transition(
    client: TestClient,
    headers: dict[str, str],
    homework: dict[str, object],
    target: str,
    **fields: object,
):
    response = client.post(
        f"/api/v1/homeworks/{homework['id']}/transitions",
        json={"expected_version": homework["version"], "status": target, **fields},
        headers=headers,
    )
    if response.status_code == 200:
        homework.update(response.json())
    return response


def test_openapi_contains_meeting_and_homework_operations(learning_api) -> None:
    client, _ = learning_api
    schema = client.app.openapi()
    expected = {
        ("get", "/api/v1/students/{student_id}/meetings"),
        ("post", "/api/v1/students/{student_id}/meetings"),
        ("get", "/api/v1/meetings/{meeting_id}"),
        ("patch", "/api/v1/meetings/{meeting_id}"),
        ("post", "/api/v1/meetings/{meeting_id}/archive"),
        ("post", "/api/v1/meetings/{meeting_id}/restore"),
        ("get", "/api/v1/strategies/{strategy_id}/homeworks"),
        ("post", "/api/v1/strategies/{strategy_id}/homeworks"),
        ("get", "/api/v1/homeworks/{homework_id}"),
        ("patch", "/api/v1/homeworks/{homework_id}"),
        ("post", "/api/v1/homeworks/{homework_id}/transitions"),
        ("get", "/api/v1/homeworks/{homework_id}/history"),
        ("post", "/api/v1/homeworks/{homework_id}/archive"),
        ("post", "/api/v1/homeworks/{homework_id}/restore"),
    }
    actual = {
        (method, path)
        for path, path_item in schema["paths"].items()
        for method in path_item
        if method in {"get", "post", "patch"}
        and (
            path.startswith(("/api/v1/meetings", "/api/v1/homeworks"))
            or path.startswith("/api/v1/students/")
            and path.endswith("/meetings")
            or path.startswith("/api/v1/strategies/")
            and path.endswith("/homeworks")
        )
    }
    assert actual == expected


def test_meeting_crud_rbac_and_archive(learning_api) -> None:
    client, factory = learning_api
    owner = add_user(client, factory, "owner", owner=True)
    curator = add_user(client, factory, "curator")
    outsider = add_user(client, factory, "outsider")
    student_user = add_user(client, factory, "student", role=UserRole.STUDENT)
    other_user = add_user(client, factory, "other-student", role=UserRole.STUDENT)
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица", user=student_user)
    other = add_student(factory, group, "Другая", user=other_user)

    missing_csrf = client.post(
        f"/api/v1/students/{student.id}/meetings",
        json={"date": "2026-10-26", "title": "Встреча"},
        headers={"Origin": "http://testserver"},
    )
    assert missing_csrf.status_code == 401

    curator_headers = authenticate(client, curator.login)
    missing_csrf = client.post(
        f"/api/v1/students/{student.id}/meetings",
        json={"date": "2026-10-26", "title": "Встреча"},
        headers={"Origin": "http://testserver"},
    )
    assert missing_csrf.status_code == 403
    created = client.post(
        f"/api/v1/students/{student.id}/meetings",
        json={
            "date": "2026-10-26",
            "title": "Разбор портфолио",
            "summary": "Обсудили кейс",
            "notes": "Внутренняя заметка",
        },
        headers=curator_headers,
    )
    assert created.status_code == 201, created.text
    meeting = created.json()

    outsider_headers = authenticate(client, outsider.login)
    assert (
        client.get(f"/api/v1/meetings/{meeting['id']}", headers=outsider_headers).status_code == 200
    )
    assert (
        client.patch(
            f"/api/v1/meetings/{meeting['id']}",
            json={"expected_version": meeting["version"], "summary": "Подмена"},
            headers=outsider_headers,
        ).status_code
        == 403
    )

    student_headers = authenticate(client, student_user.login)
    own = client.get(f"/api/v1/meetings/{meeting['id']}", headers=student_headers)
    assert own.status_code == 200
    assert "notes" not in own.json()
    assert (
        client.get(f"/api/v1/students/{other.id}/meetings", headers=student_headers).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/meetings/{meeting['id']}",
            json={"expected_version": meeting["version"], "summary": "Подмена"},
            headers=student_headers,
        ).status_code
        == 403
    )

    owner_headers = authenticate(client, owner.login)
    updated = client.patch(
        f"/api/v1/meetings/{meeting['id']}",
        json={"expected_version": meeting["version"], "summary": "Новый итог"},
        headers=owner_headers,
    )
    assert updated.status_code == 200
    archived = client.post(
        f"/api/v1/meetings/{meeting['id']}/archive",
        json={"expected_version": updated.json()["version"]},
        headers=owner_headers,
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    restored = client.post(
        f"/api/v1/meetings/{meeting['id']}/restore",
        json={"expected_version": archived.json()["version"]},
        headers=owner_headers,
    )
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None

    listing = client.get(f"/api/v1/students/{student.id}/meetings", headers=student_headers)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["items"]] == [meeting["id"]]


def test_homework_snapshot_cross_strategy_and_issue_do_not_complete_tasks(learning_api) -> None:
    client, factory = learning_api
    curator = add_user(client, factory, "curator")
    group = add_group(factory, curator)
    first_student = add_student(factory, group, "Первая")
    second_student = add_student(factory, group, "Вторая")
    first_task = add_strategy_task(factory, first_student, "Собрать кейс")
    second_task = add_strategy_task(factory, second_student, "Чужая задача")
    headers = authenticate(client, curator.login)

    cross_strategy = client.post(
        f"/api/v1/strategies/{first_task.strategy_id}/homeworks",
        json={"title": "ДЗ", "task_ids": [first_task.id, second_task.id]},
        headers=headers,
    )
    assert cross_strategy.status_code == 422

    homework = create_homework(client, headers, first_task)
    item = homework["items"][0]
    assert item["title"] == "Собрать кейс"
    assert item["description"] == "Исходное описание"
    assert item["materials"] == ["Материал"]

    with factory.begin() as database:
        task = database.get(StrategyTask, first_task.id)
        task.title = "Изменённая задача"
        task.description = "Новое описание"

    read = client.get(f"/api/v1/homeworks/{homework['id']}", headers=headers).json()
    assert read["items"][0]["title"] == "Собрать кейс"
    issued = transition(client, headers, homework, "issued")
    assert issued.status_code == 200
    immutable = client.patch(
        f"/api/v1/homeworks/{homework['id']}",
        json={"expected_version": homework["version"], "title": "Подмена"},
        headers=headers,
    )
    assert immutable.status_code == 409

    with factory() as database:
        task_version = database.get(StrategyTask, first_task.id).version
    archived_task = client.post(
        f"/api/v1/strategy-tasks/{first_task.id}/archive",
        json={"expected_version": task_version},
        headers=headers,
    )
    assert archived_task.status_code == 200
    assert (
        client.get(f"/api/v1/homeworks/{homework['id']}", headers=headers).json()["items"][0][
            "title"
        ]
        == "Собрать кейс"
    )

    with factory() as database:
        task = database.get(StrategyTask, first_task.id)
        assert task.study_status is StudyStatus.NOT_STARTED
        assert task.review_status.value == "none"
        item_row = database.scalar(select(HomeworkItem))
        item_row.title = "Попытка подмены"
        with pytest.raises(IntegrityError):
            database.commit()


def test_homework_submit_revision_accept_and_review_lock(learning_api) -> None:
    client, factory = learning_api
    curator = add_user(client, factory, "curator")
    student_user = add_user(client, factory, "student", role=UserRole.STUDENT)
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица", user=student_user)
    task = add_strategy_task(factory, student, "Собрать кейс")
    with factory.begin() as database:
        database.add(
            AnyaApproval(
                task_id=task.id,
                status=ApprovalStatus.SENT,
                comment="Независимое согласование",
            )
        )
    curator_headers = authenticate(client, curator.login)
    homework = create_homework(client, curator_headers, task)
    assert transition(client, curator_headers, homework, "issued").status_code == 200

    student_headers = authenticate(client, student_user.login)
    submitted = transition(
        client,
        student_headers,
        homework,
        "submitted",
        submission_text="Готовая работа",
        submission_links={"work": "https://example.com/work"},
    )
    assert submitted.status_code == 200
    assert transition(client, student_headers, homework, "accepted").status_code == 403
    with factory() as database:
        current_task = database.get(StrategyTask, task.id)
        assert current_task.study_status is StudyStatus.IN_PROGRESS
        assert current_task.review_status.value == "pending"
        task_version = current_task.version

    curator_headers = authenticate(client, curator.login)
    blocked = client.post(
        f"/api/v1/strategy-tasks/{task.id}/study-status",
        json={"expected_version": task_version, "study_status": "done"},
        headers=curator_headers,
    )
    assert blocked.status_code == 409, blocked.text

    revision = transition(
        client,
        curator_headers,
        homework,
        "revision",
        curator_feedback="Добавить детали",
    )
    assert revision.status_code == 200
    with factory() as database:
        revision_task_version = database.get(StrategyTask, task.id).version
    revision_locked = client.post(
        f"/api/v1/strategy-tasks/{task.id}/study-status",
        json={"expected_version": revision_task_version, "study_status": "hold"},
        headers=curator_headers,
    )
    assert revision_locked.status_code == 409
    assert revision_locked.json()["error"]["code"] == "homework_review_pending"
    student_headers = authenticate(client, student_user.login)
    resubmitted = transition(
        client,
        student_headers,
        homework,
        "submitted",
        submission_text="Исправленная работа",
    )
    assert resubmitted.status_code == 200
    curator_headers = authenticate(client, curator.login)
    accepted = transition(
        client,
        curator_headers,
        homework,
        "accepted",
        curator_feedback="Принято",
    )
    assert accepted.status_code == 200

    with factory() as database:
        current_task = database.get(StrategyTask, task.id)
        assert current_task.study_status is StudyStatus.DONE
        assert current_task.review_status.value == "accepted"
        approval = database.scalar(select(AnyaApproval).where(AnyaApproval.task_id == task.id))
        assert approval.status is ApprovalStatus.SENT
        assert approval.comment == "Независимое согласование"
        assert approval.version == 1
        events = list(
            database.scalars(
                select(HomeworkHistory)
                .where(HomeworkHistory.homework_id == homework["id"])
                .order_by(HomeworkHistory.created_at, HomeworkHistory.id)
            )
        )
        assert [event.to_status.value for event in events if event.to_status is not None] == [
            "issued",
            "submitted",
            "revision",
            "submitted",
            "accepted",
        ]
    duplicate = transition(client, curator_headers, homework, "accepted")
    assert duplicate.status_code == 409


def test_task_cannot_have_two_active_homework_reviews(learning_api) -> None:
    client, factory = learning_api
    curator = add_user(client, factory, "curator")
    student_user = add_user(client, factory, "student", role=UserRole.STUDENT)
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица", user=student_user)
    task = add_strategy_task(factory, student, "Одна задача")
    curator_headers = authenticate(client, curator.login)
    first = create_homework(client, curator_headers, task)
    second = create_homework(client, curator_headers, task)
    assert transition(client, curator_headers, first, "issued").status_code == 200
    assert transition(client, curator_headers, second, "issued").status_code == 200

    student_headers = authenticate(client, student_user.login)
    assert (
        transition(
            client,
            student_headers,
            first,
            "submitted",
            submission_text="Первая работа",
        ).status_code
        == 200
    )
    conflict = transition(
        client,
        student_headers,
        second,
        "submitted",
        submission_text="Вторая работа",
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "task_review_conflict"

    curator_headers = authenticate(client, curator.login)
    assert transition(client, curator_headers, first, "revision").status_code == 200
    student_headers = authenticate(client, student_user.login)
    assert transition(client, student_headers, first, "progress").status_code == 200
    curator_headers = authenticate(client, curator.login)
    archive = client.post(
        f"/api/v1/homeworks/{first['id']}/archive",
        json={"expected_version": first["version"]},
        headers=curator_headers,
    )
    assert archive.status_code == 409
    assert archive.json()["error"]["code"] == "homework_review_active"

    with factory() as database:
        first_row = database.get(Homework, first["id"])
        second_row = database.get(Homework, second["id"])
        current_task = database.get(StrategyTask, task.id)
        assert first_row.status is HomeworkStatus.PROGRESS
        assert first_row.archived_at is None
        assert second_row.status is HomeworkStatus.ISSUED
        assert current_task.review_status.value == "revision"


def test_homework_student_scope_mass_assignment_and_private_history(learning_api) -> None:
    client, factory = learning_api
    curator = add_user(client, factory, "curator")
    outsider = add_user(client, factory, "outsider")
    first_user = add_user(client, factory, "first", role=UserRole.STUDENT)
    second_user = add_user(client, factory, "second", role=UserRole.STUDENT)
    group = add_group(factory, curator)
    first = add_student(factory, group, "Первая", user=first_user)
    second = add_student(factory, group, "Вторая", user=second_user)
    first_task = add_strategy_task(factory, first, "Первая задача")
    second_task = add_strategy_task(factory, second, "Вторая задача")
    curator_headers = authenticate(client, curator.login)
    first_homework = create_homework(client, curator_headers, first_task)
    second_homework = create_homework(client, curator_headers, second_task)
    assert transition(client, curator_headers, first_homework, "issued").status_code == 200

    outsider_headers = authenticate(client, outsider.login)
    assert (
        transition(
            client,
            outsider_headers,
            first_homework,
            "submitted",
            submission_text="Подмена",
        ).status_code
        == 403
    )

    student_headers = authenticate(client, first_user.login)
    assert (
        client.get(f"/api/v1/homeworks/{first_homework['id']}", headers=student_headers).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/homeworks/{second_homework['id']}", headers=student_headers
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/strategies/{second_task.strategy_id}/homeworks", headers=student_headers
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/homeworks/{first_homework['id']}",
            json={"expected_version": first_homework["version"], "curator_feedback": "Подмена"},
            headers=student_headers,
        ).status_code
        == 422
    )
    history = client.get(
        f"/api/v1/homeworks/{first_homework['id']}/history", headers=student_headers
    )
    assert history.status_code == 200
    assert "actor_user_id" not in history.json()["items"][0]
    curator_headers = authenticate(client, curator.login)
    assert (
        client.post(
            f"/api/v1/strategies/{first_task.strategy_id}/homeworks",
            json={
                "title": "Подмена",
                "task_ids": [first_task.id],
                "strategy_id": second_task.strategy_id,
                "status": "accepted",
            },
            headers=curator_headers,
        ).status_code
        == 422
    )


def test_homework_archive_restore_preserves_items_and_history(learning_api) -> None:
    client, factory = learning_api
    curator = add_user(client, factory, "curator")
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица")
    task = add_strategy_task(factory, student, "Задача")
    headers = authenticate(client, curator.login)
    homework = create_homework(client, headers, task)
    assert transition(client, headers, homework, "issued").status_code == 200
    archived = client.post(
        f"/api/v1/homeworks/{homework['id']}/archive",
        json={"expected_version": homework["version"]},
        headers=headers,
    )
    assert archived.status_code == 200
    restored = client.post(
        f"/api/v1/homeworks/{homework['id']}/restore",
        json={"expected_version": archived.json()["version"]},
        headers=headers,
    )
    assert restored.status_code == 200
    assert len(restored.json()["items"]) == 1
    history = client.get(f"/api/v1/homeworks/{homework['id']}/history", headers=headers)
    assert len(history.json()["items"]) == 4


def test_stale_versions_curator_reassignment_and_concurrent_submission(learning_api) -> None:
    client, factory = learning_api
    add_user(client, factory, "owner", owner=True)
    curator = add_user(client, factory, "curator")
    replacement = add_user(client, factory, "replacement")
    student_user = add_user(client, factory, "student", role=UserRole.STUDENT)
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица", user=student_user)
    task = add_strategy_task(factory, student, "Задача")
    curator_headers = authenticate(client, curator.login)
    homework = create_homework(client, curator_headers, task)
    assert transition(client, curator_headers, homework, "issued").status_code == 200

    stale = client.patch(
        f"/api/v1/homeworks/{homework['id']}",
        json={"expected_version": 1, "description": "Устаревшая правка"},
        headers=curator_headers,
    )
    assert stale.status_code == 409

    with factory.begin() as database:
        database.execute(
            update(Group)
            .where(Group.id == group.id)
            .values(curator_id=replacement.id, version=Group.version + 1)
        )
    denied = client.post(
        f"/api/v1/homeworks/{homework['id']}/archive",
        json={"expected_version": homework["version"]},
        headers=curator_headers,
    )
    assert denied.status_code == 403

    first_client = TestClient(client.app)
    second_client = TestClient(client.app)
    first_headers = authenticate(first_client, student_user.login)
    second_headers = authenticate(second_client, student_user.login)
    barrier = Barrier(2)

    def submit(test_client: TestClient, headers: dict[str, str]) -> int:
        barrier.wait()
        return test_client.post(
            f"/api/v1/homeworks/{homework['id']}/transitions",
            json={
                "expected_version": homework["version"],
                "status": "submitted",
                "submission_text": "Работа",
            },
            headers=headers,
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = [
                future.result()
                for future in (
                    executor.submit(submit, first_client, first_headers),
                    executor.submit(submit, second_client, second_headers),
                )
            ]
    finally:
        first_client.close()
        second_client.close()
    assert sorted(statuses) == [200, 409]
    with factory() as database:
        history_count = len(
            list(
                database.scalars(
                    select(HomeworkHistory).where(
                        HomeworkHistory.homework_id == homework["id"],
                        HomeworkHistory.to_status == HomeworkStatus.SUBMITTED,
                    )
                )
            )
        )
        assert history_count == 1


def test_concurrent_homeworks_cannot_review_the_same_task(learning_api) -> None:
    client, factory = learning_api
    curator = add_user(client, factory, "curator")
    student_user = add_user(client, factory, "student", role=UserRole.STUDENT)
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица", user=student_user)
    task = add_strategy_task(factory, student, "Общая задача")
    curator_headers = authenticate(client, curator.login)
    first = create_homework(client, curator_headers, task)
    second = create_homework(client, curator_headers, task)
    assert transition(client, curator_headers, first, "issued").status_code == 200
    assert transition(client, curator_headers, second, "issued").status_code == 200

    first_client = TestClient(client.app)
    second_client = TestClient(client.app)
    first_headers = authenticate(first_client, student_user.login)
    second_headers = authenticate(second_client, student_user.login)
    barrier = Barrier(2)

    def submit(
        test_client: TestClient,
        headers: dict[str, str],
        homework: dict[str, object],
    ) -> int:
        barrier.wait()
        return test_client.post(
            f"/api/v1/homeworks/{homework['id']}/transitions",
            json={
                "expected_version": homework["version"],
                "status": "submitted",
                "submission_text": "Работа",
            },
            headers=headers,
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = [
                future.result()
                for future in (
                    executor.submit(submit, first_client, first_headers, first),
                    executor.submit(submit, second_client, second_headers, second),
                )
            ]
    finally:
        first_client.close()
        second_client.close()

    assert sorted(statuses) == [200, 409]
    with factory() as database:
        homeworks = [database.get(Homework, item["id"]) for item in (first, second)]
        assert sorted(homework.status.value for homework in homeworks) == ["issued", "submitted"]
        assert sorted(homework.version for homework in homeworks) == [2, 3]
        assert sorted(homework.submission_text for homework in homeworks) == ["", "Работа"]
        history_counts = [
            len(
                list(
                    database.scalars(
                        select(HomeworkHistory).where(HomeworkHistory.homework_id == homework.id)
                    )
                )
            )
            for homework in homeworks
        ]
        assert sorted(history_counts) == [2, 3]
        current_task = database.get(StrategyTask, task.id)
        assert current_task.review_status.value == "pending"
        assert current_task.study_status is StudyStatus.IN_PROGRESS
        assert current_task.version == 2
        assert (
            len(list(database.scalars(select(TaskHistory).where(TaskHistory.task_id == task.id))))
            == 1
        )
        transition_audits = list(
            database.scalars(
                select(AuditEvent).where(
                    AuditEvent.target_group_id == group.id,
                    AuditEvent.action == AuditAction.HOMEWORK_TRANSITIONED,
                )
            )
        )
        assert len(transition_audits) == 3


@pytest.mark.parametrize("first_operation", ["manual", "submission"])
def test_task_status_and_homework_submission_are_linearizable(
    learning_api, first_operation: str
) -> None:
    client, factory = learning_api
    curator = add_user(client, factory, "curator")
    student_user = add_user(client, factory, "student", role=UserRole.STUDENT)
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица", user=student_user)
    task = add_strategy_task(factory, student, "Задача")
    curator_headers = authenticate(client, curator.login)
    homework = create_homework(client, curator_headers, task)
    assert transition(client, curator_headers, homework, "issued").status_code == 200

    submit_client = TestClient(client.app)
    status_client = TestClient(client.app)
    student_headers = authenticate(submit_client, student_user.login)
    curator_headers = authenticate(status_client, curator.login)
    first_finished = Event()

    def submit():
        if first_operation == "manual":
            assert first_finished.wait(timeout=10)
        response = submit_client.post(
            f"/api/v1/homeworks/{homework['id']}/transitions",
            json={
                "expected_version": homework["version"],
                "status": "submitted",
                "submission_text": "Работа",
            },
            headers=student_headers,
        )
        if first_operation == "submission":
            first_finished.set()
        return response

    def change_status():
        if first_operation == "submission":
            assert first_finished.wait(timeout=10)
        response = status_client.post(
            f"/api/v1/strategy-tasks/{task.id}/study-status",
            json={"expected_version": task.version, "study_status": "in_progress"},
            headers=curator_headers,
        )
        if first_operation == "manual":
            first_finished.set()
        return response

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(submit), executor.submit(change_status)]
            submit_response, status_response = [future.result() for future in futures]
    finally:
        submit_client.close()
        status_client.close()

    assert submit_response.status_code == 200
    if first_operation == "manual":
        assert status_response.status_code == 200
    else:
        assert status_response.status_code == 409
        assert status_response.json()["error"]["code"] == "homework_review_pending"

    with factory() as database:
        current_homework = database.get(Homework, homework["id"])
        current_task = database.get(StrategyTask, task.id)
        assert current_homework.status is HomeworkStatus.SUBMITTED
        assert current_task.study_status is StudyStatus.IN_PROGRESS
        assert current_task.review_status.value == "pending"
        assert current_homework.version == 3
        assert current_task.version == (3 if first_operation == "manual" else 2)
        task_events = list(
            database.scalars(
                select(TaskHistory)
                .where(TaskHistory.task_id == task.id)
                .order_by(TaskHistory.created_at, TaskHistory.id)
            )
        )
        expected_events = ["homework_submitted"]
        if first_operation == "manual":
            expected_events.insert(0, "study_status_changed")
        assert [event.event_type for event in task_events] == expected_events
        homework_events = list(
            database.scalars(
                select(HomeworkHistory).where(HomeworkHistory.homework_id == homework["id"])
            )
        )
        assert len(homework_events) == 3
        relevant_audits = list(
            database.scalars(
                select(AuditEvent).where(
                    AuditEvent.target_group_id == group.id,
                    AuditEvent.action.in_(
                        [AuditAction.TASK_STATUS_CHANGED, AuditAction.HOMEWORK_TRANSITIONED]
                    ),
                )
            )
        )
        assert len(relevant_audits) == (3 if first_operation == "manual" else 2)
        task_version = current_task.version
        task_history_count = len(task_events)
        audit_count = len(relevant_audits)

    locked_headers = authenticate(client, curator.login)
    locked = client.post(
        f"/api/v1/strategy-tasks/{task.id}/study-status",
        json={"expected_version": task_version, "study_status": "hold"},
        headers=locked_headers,
    )
    assert locked.status_code == 409
    assert locked.json()["error"]["code"] == "homework_review_pending"
    with factory() as database:
        current_task = database.get(StrategyTask, task.id)
        assert current_task.version == task_version
        assert current_task.study_status is StudyStatus.IN_PROGRESS
        assert current_task.review_status.value == "pending"
        assert (
            len(list(database.scalars(select(TaskHistory).where(TaskHistory.task_id == task.id))))
            == task_history_count
        )
        assert (
            len(
                list(
                    database.scalars(
                        select(AuditEvent).where(
                            AuditEvent.target_group_id == group.id,
                            AuditEvent.action.in_(
                                [AuditAction.TASK_STATUS_CHANGED, AuditAction.HOMEWORK_TRANSITIONED]
                            ),
                        )
                    )
                )
            )
            == audit_count
        )


def test_concurrent_acceptance_and_revision_keep_task_consistent(learning_api) -> None:
    client, factory = learning_api
    curator = add_user(client, factory, "curator")
    student_user = add_user(client, factory, "student", role=UserRole.STUDENT)
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица", user=student_user)
    task = add_strategy_task(factory, student, "Задача")
    curator_headers = authenticate(client, curator.login)
    homework = create_homework(client, curator_headers, task)
    assert transition(client, curator_headers, homework, "issued").status_code == 200
    student_headers = authenticate(client, student_user.login)
    assert (
        transition(
            client,
            student_headers,
            homework,
            "submitted",
            submission_text="Работа",
        ).status_code
        == 200
    )

    accept_client = TestClient(client.app)
    revision_client = TestClient(client.app)
    accept_headers = authenticate(accept_client, curator.login)
    revision_headers = authenticate(revision_client, curator.login)
    barrier = Barrier(2)

    def decide(test_client: TestClient, headers: dict[str, str], target: str) -> int:
        barrier.wait()
        return test_client.post(
            f"/api/v1/homeworks/{homework['id']}/transitions",
            json={"expected_version": homework["version"], "status": target},
            headers=headers,
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(decide, accept_client, accept_headers, "accepted"),
                executor.submit(decide, revision_client, revision_headers, "revision"),
            ]
            statuses = [future.result() for future in futures]
    finally:
        accept_client.close()
        revision_client.close()

    assert sorted(statuses) == [200, 409]
    with factory() as database:
        current_homework = database.get(Homework, homework["id"])
        current_task = database.get(StrategyTask, task.id)
        if current_homework.status is HomeworkStatus.ACCEPTED:
            assert current_task.study_status is StudyStatus.DONE
            assert current_task.review_status.value == "accepted"
        else:
            assert current_homework.status is HomeworkStatus.REVISION
            assert current_task.study_status is StudyStatus.IN_PROGRESS
            assert current_task.review_status.value == "revision"


def test_homework_history_and_items_are_append_only(learning_api) -> None:
    client, factory = learning_api
    curator = add_user(client, factory, "curator")
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица")
    task = add_strategy_task(factory, student, "Задача")
    headers = authenticate(client, curator.login)
    homework = create_homework(client, headers, task)
    assert transition(client, headers, homework, "issued").status_code == 200

    with factory() as database:
        history = database.scalar(select(HomeworkHistory))
        with pytest.raises(IntegrityError):
            database.execute(
                update(HomeworkHistory)
                .where(HomeworkHistory.id == history.id)
                .values(event_type="x")
            )
    with factory() as database:
        item = database.scalar(select(HomeworkItem))
        database.delete(item)
        with pytest.raises(IntegrityError):
            database.commit()


def test_homework_rollback_if_history_insert_fails(learning_api, monkeypatch) -> None:
    client, factory = learning_api
    curator = add_user(client, factory, "curator")
    group = add_group(factory, curator)
    student = add_student(factory, group, "Ученица")
    task = add_strategy_task(factory, student, "Задача")
    headers = authenticate(client, curator.login)
    homework = create_homework(client, headers, task)

    from app.modules.homeworks import service as homework_service

    original_history = homework_service._history

    def broken_history(*args, **kwargs):
        original_history(*args, **kwargs)
        raise RuntimeError("history failure")

    monkeypatch.setattr(homework_service, "_history", broken_history)
    with pytest.raises(RuntimeError):
        transition(client, headers, homework, "issued")

    with factory() as database:
        current = database.get(Homework, homework["id"])
        assert current.status is HomeworkStatus.DRAFT
        assert len(list(database.scalars(select(HomeworkHistory)))) == 1
