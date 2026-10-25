from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine, get_db
from app.main import create_app
from app.modules.auth.models import AuthSession
from app.modules.auth.passwords import PasswordManager
from app.modules.groups.models import Group, GroupStatus
from app.modules.students.models import Student
from app.modules.users.audit import AuditEvent
from app.modules.users.models import User, UserRole

PASSWORD = "correct horse battery staple"


@pytest.fixture
def business_api(tmp_path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'business-api.db').as_posix()}"
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
    active: bool = True,
    must_change_password: bool = False,
) -> User:
    manager: PasswordManager = client.app.state.password_manager
    user = User(
        login=login,
        role=role,
        password_hash=manager.hash(PASSWORD),
        is_owner=owner,
        is_active=active,
        must_change_password=must_change_password,
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


def group_payload(name: str = "Новая группа") -> dict[str, object]:
    return {"name": name, "starts_at": "2026-11-01", "notes": "Заметка"}


def test_owner_and_admin_create_self_assigned_groups(business_api) -> None:
    client, factory = business_api
    owner = add_user(client, factory, "owner", owner=True)
    admin = add_user(client, factory, "admin")

    owner_headers = authenticate(client, owner.login)
    owner_response = client.post(
        "/api/v1/groups", json=group_payload("Owner"), headers=owner_headers
    )
    admin_headers = authenticate(client, admin.login)
    admin_response = client.post(
        "/api/v1/groups", json=group_payload("Admin"), headers=admin_headers
    )

    assert owner_response.status_code == 201
    assert admin_response.status_code == 201
    assert owner_response.json()["curator_id"] == owner.id
    assert admin_response.json()["curator_id"] == admin.id
    assert owner_response.json()["status"] == "backlog"
    with factory() as database:
        assert database.scalar(select(Group).where(Group.name == "Owner")).curator_id == owner.id
        assert database.scalar(select(Group).where(Group.name == "Admin")).curator_id == admin.id


def test_group_creation_rejects_student_csrf_and_mass_assignment(business_api) -> None:
    client, factory = business_api
    admin = add_user(client, factory, "admin")
    student = add_user(client, factory, "student", role=UserRole.STUDENT)

    student_headers = authenticate(client, student.login)
    assert (
        client.post("/api/v1/groups", json=group_payload(), headers=student_headers).status_code
        == 403
    )
    admin_headers = authenticate(client, admin.login)
    assert client.post("/api/v1/groups", json=group_payload()).status_code == 403
    response = client.post(
        "/api/v1/groups",
        json={**group_payload(), "curator_id": student.id},
        headers=admin_headers,
    )
    assert response.status_code == 422
    with factory() as database:
        assert database.scalar(select(Group)) is None


def test_admin_reads_all_groups_but_updates_only_assigned_group(business_api) -> None:
    client, factory = business_api
    first = add_user(client, factory, "first")
    second = add_user(client, factory, "second")
    own = add_group(factory, first, "Своя")
    foreign = add_group(factory, second, "Чужая")
    headers = authenticate(client, first.login)

    listing = client.get("/api/v1/groups", headers=headers)
    own_patch = client.patch(
        f"/api/v1/groups/{own.id}",
        json={"expected_version": 1, "name": "Обновлённая"},
        headers=headers,
    )
    foreign_patch = client.patch(
        f"/api/v1/groups/{foreign.id}",
        json={"expected_version": 1, "name": "Нельзя"},
        headers=headers,
    )

    assert listing.status_code == 200
    assert {item["id"] for item in listing.json()["items"]} == {own.id, foreign.id}
    assert own_patch.status_code == 200
    assert foreign_patch.status_code == 403


def test_student_sees_only_own_group_and_profile(business_api) -> None:
    client, factory = business_api
    curator = add_user(client, factory, "curator")
    own_user = add_user(client, factory, "student.one", role=UserRole.STUDENT)
    other_user = add_user(client, factory, "student.two", role=UserRole.STUDENT)
    own_group = add_group(factory, curator, "Своя группа")
    other_group = add_group(factory, curator, "Чужая группа")
    own_student = add_student(factory, own_group, "Первая", user=own_user)
    other_student = add_student(factory, other_group, "Вторая", user=other_user)
    headers = authenticate(client, own_user.login)

    listing = client.get("/api/v1/groups", headers=headers)
    own = client.get(f"/api/v1/students/{own_student.id}", headers=headers)
    foreign = client.get(f"/api/v1/students/{other_student.id}", headers=headers)
    foreign_group = client.get(f"/api/v1/groups/{other_group.id}", headers=headers)

    assert [item["id"] for item in listing.json()["items"]] == [own_group.id]
    assert "curator_id" not in listing.json()["items"][0]
    assert own.status_code == 200
    assert foreign.status_code == 404
    assert foreign_group.status_code == 404
    assert "personal_notes" not in own.json()


def test_group_archive_restore_preserves_students_and_requires_current_version(
    business_api,
) -> None:
    client, factory = business_api
    admin = add_user(client, factory, "admin")
    group = add_group(factory, admin)
    student = add_student(factory, group, "Ученица")
    headers = authenticate(client, admin.login)

    archived = client.post(
        f"/api/v1/groups/{group.id}/archive",
        json={"expected_version": 1},
        headers=headers,
    )
    stale_restore = client.post(
        f"/api/v1/groups/{group.id}/restore",
        json={"expected_version": 1},
        headers=headers,
    )
    restored = client.post(
        f"/api/v1/groups/{group.id}/restore",
        json={"expected_version": 2},
        headers=headers,
    )

    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["status_before_archive"] == "active"
    assert stale_restore.status_code == 409
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    with factory() as database:
        assert database.get(Student, student.id) is not None


def test_student_patch_is_partial_merges_links_and_detects_lost_update(business_api) -> None:
    client, factory = business_api
    admin = add_user(client, factory, "admin")
    group = add_group(factory, admin)
    student = add_student(factory, group, "Ученица")
    with factory.begin() as database:
        persisted = database.get(Student, student.id)
        persisted.personal_notes = "Сохранить"
        persisted.links = {"portfolio": "https://example.com/portfolio"}
    headers = authenticate(client, admin.login)

    first = client.patch(
        f"/api/v1/students/{student.id}",
        json={
            "expected_version": 1,
            "point_a": "Новая точка",
            "links": {"resume": "https://example.com/resume"},
        },
        headers=headers,
    )
    stale = client.patch(
        f"/api/v1/students/{student.id}",
        json={"expected_version": 1, "point_b": "Тихая перезапись"},
        headers=headers,
    )

    assert first.status_code == 200
    assert first.json()["links"] == {
        "portfolio": "https://example.com/portfolio",
        "resume": "https://example.com/resume",
    }
    assert first.json()["personal_notes"] == "Сохранить"
    assert stale.status_code == 409
    with factory() as database:
        persisted = database.get(Student, student.id)
        assert persisted.point_a == "Новая точка"
        assert persisted.point_b == ""


def test_student_create_uses_url_group_and_records_safe_audit(business_api) -> None:
    client, factory = business_api
    admin = add_user(client, factory, "admin")
    group = add_group(factory, admin)
    headers = authenticate(client, admin.login)

    forbidden = client.post(
        f"/api/v1/groups/{group.id}/students",
        json={"name": "Ученица", "group_id": "other", "user_id": "other"},
        headers=headers,
    )
    created = client.post(
        f"/api/v1/groups/{group.id}/students",
        json={"name": "Ученица", "personal_notes": "Секретная заметка"},
        headers=headers,
    )

    assert forbidden.status_code == 422
    assert created.status_code == 201
    assert created.json()["group_id"] == group.id
    assert created.json()["user_id"] is None
    with factory() as database:
        event = database.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc())).first()
        assert event.actor_user_id == admin.id
        assert event.target_group_id == group.id
        assert event.details == {"student_id": created.json()["id"]}
        assert "Секретная заметка" not in str(event.details)


def test_openapi_contains_groups_and_students_operations(business_api) -> None:
    client, _ = business_api
    schema = client.app.openapi()

    expected = {
        ("get", "/api/v1/groups"),
        ("post", "/api/v1/groups"),
        ("get", "/api/v1/groups/{group_id}"),
        ("patch", "/api/v1/groups/{group_id}"),
        ("post", "/api/v1/groups/{group_id}/archive"),
        ("post", "/api/v1/groups/{group_id}/restore"),
        ("get", "/api/v1/groups/{group_id}/students"),
        ("post", "/api/v1/groups/{group_id}/students"),
        ("get", "/api/v1/students/{student_id}"),
        ("patch", "/api/v1/students/{student_id}"),
        ("post", "/api/v1/students/{student_id}/archive"),
        ("post", "/api/v1/students/{student_id}/restore"),
        ("get", "/api/v1/students/{student_id}/strategy"),
        ("post", "/api/v1/students/{student_id}/strategy"),
        ("get", "/api/v1/students/{student_id}/meetings"),
        ("post", "/api/v1/students/{student_id}/meetings"),
    }
    actual = {
        (method, path)
        for path, path_item in schema["paths"].items()
        for method in path_item
        if path.startswith(("/api/v1/groups", "/api/v1/students"))
        and method in {"get", "post", "patch"}
    }
    assert actual == expected


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    (
        ("GET", "/api/v1/groups", None),
        ("POST", "/api/v1/groups", group_payload()),
        ("GET", "/api/v1/groups/missing", None),
        ("PATCH", "/api/v1/groups/missing", {"expected_version": 1, "name": "X"}),
        ("POST", "/api/v1/groups/missing/archive", {"expected_version": 1}),
        ("POST", "/api/v1/groups/missing/restore", {"expected_version": 1}),
        ("GET", "/api/v1/groups/missing/students", None),
        ("POST", "/api/v1/groups/missing/students", {"name": "X"}),
        ("GET", "/api/v1/students/missing", None),
        ("PATCH", "/api/v1/students/missing", {"expected_version": 1, "name": "X"}),
        ("POST", "/api/v1/students/missing/archive", {"expected_version": 1}),
        ("POST", "/api/v1/students/missing/restore", {"expected_version": 1}),
    ),
)
def test_every_business_endpoint_requires_authentication(
    business_api,
    method: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    client, _ = business_api
    kwargs = {"json": payload} if payload is not None else {}

    response = client.request(method, path, **kwargs)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize("must_change_password", (False, True))
def test_inactive_and_password_change_required_actors_are_blocked(
    business_api,
    must_change_password: bool,
) -> None:
    client, factory = business_api
    actor = add_user(
        client,
        factory,
        f"blocked-{must_change_password}",
        must_change_password=must_change_password,
    )
    headers = authenticate(client, actor.login)
    if not must_change_password:
        with factory.begin() as database:
            database.get(User, actor.id).is_active = False

    response = client.get("/api/v1/groups", headers=headers)

    assert response.status_code == (403 if must_change_password else 401)


def test_revoked_session_blocks_business_access(business_api) -> None:
    client, factory = business_api
    actor = add_user(client, factory, "revoked")
    headers = authenticate(client, actor.login)
    with factory.begin() as database:
        auth_session = database.scalar(select(AuthSession).where(AuthSession.user_id == actor.id))
        auth_session.revoked_at = datetime(2026, 10, 25, 12, 0)

    response = client.get("/api/v1/groups", headers=headers)

    assert response.status_code == 401


def test_expired_session_blocks_business_access(business_api) -> None:
    client, factory = business_api
    actor = add_user(client, factory, "expired")
    headers = authenticate(client, actor.login)
    with factory.begin() as database:
        auth_session = database.scalar(select(AuthSession).where(AuthSession.user_id == actor.id))
        auth_session.absolute_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    response = client.get("/api/v1/groups", headers=headers)

    assert response.status_code == 401


def test_group_list_filters_paginates_and_rejects_invalid_cursor(business_api) -> None:
    client, factory = business_api
    first = add_user(client, factory, "first")
    second = add_user(client, factory, "second")
    for index in range(3):
        group = add_group(factory, first if index < 2 else second, f"Группа {index}")
        if index == 1:
            with factory.begin() as database:
                database.get(Group, group.id).status = GroupStatus.COMPLETED
    headers = authenticate(client, first.login)

    first_page = client.get("/api/v1/groups?limit=2", headers=headers)
    second_page = client.get(
        "/api/v1/groups",
        params={"limit": 2, "cursor": first_page.json()["next_cursor"]},
        headers=headers,
    )
    filtered = client.get(
        "/api/v1/groups",
        params={"lifecycle": "completed", "curator_id": first.id},
        headers=headers,
    )
    invalid = client.get("/api/v1/groups?cursor=%25%25%25", headers=headers)
    oversized = client.get("/api/v1/groups", params={"cursor": "eHh4" * 300}, headers=headers)

    assert len(first_page.json()["items"]) == 2
    assert len(second_page.json()["items"]) == 1
    assert set(item["id"] for item in first_page.json()["items"]).isdisjoint(
        item["id"] for item in second_page.json()["items"]
    )
    assert [item["status"] for item in filtered.json()["items"]] == ["completed"]
    assert invalid.status_code == 422
    assert oversized.status_code == 422


def test_group_validation_and_server_managed_fields(business_api) -> None:
    client, factory = business_api
    admin = add_user(client, factory, "admin")
    headers = authenticate(client, admin.login)

    empty = client.post(
        "/api/v1/groups",
        json={"name": "   ", "starts_at": "2026-11-01"},
        headers=headers,
    )
    dates = client.post(
        "/api/v1/groups",
        json={"name": "X", "starts_at": "2026-11-02", "ends_at": "2026-11-01"},
        headers=headers,
    )
    actual_dates = client.post(
        "/api/v1/groups",
        json={
            "name": "X",
            "starts_at": "2026-11-02",
            "actual_ends_at": "2026-11-01",
        },
        headers=headers,
    )
    archived = client.post(
        "/api/v1/groups",
        json={"name": "X", "starts_at": "2026-11-01", "status": "archived"},
        headers=headers,
    )
    extra = client.post(
        "/api/v1/groups",
        json={**group_payload(), "id": "chosen", "is_owner": True},
        headers=headers,
    )
    group = add_group(factory, admin)
    patch_extra = client.patch(
        f"/api/v1/groups/{group.id}",
        json={"expected_version": 1, "name": "X", "curator_id": "chosen"},
        headers=headers,
    )
    patch_dates = client.patch(
        f"/api/v1/groups/{group.id}",
        json={"expected_version": 1, "actual_ends_at": "2026-09-30"},
        headers=headers,
    )

    assert {
        empty.status_code,
        dates.status_code,
        actual_dates.status_code,
        archived.status_code,
        extra.status_code,
        patch_extra.status_code,
        patch_dates.status_code,
    } == {422}


def test_owner_updates_foreign_group_and_reassignment_invalidates_old_version(business_api) -> None:
    client, factory = business_api
    owner = add_user(client, factory, "owner", owner=True)
    first = add_user(client, factory, "first")
    second = add_user(client, factory, "second")
    group = add_group(factory, first)
    headers = authenticate(client, owner.login)

    reassigned = client.post(
        f"/api/v1/admin/groups/{group.id}/reassign-curator",
        json={"curator_id": second.id},
        headers=headers,
    )
    stale = client.patch(
        f"/api/v1/groups/{group.id}",
        json={"expected_version": 1, "name": "Stale"},
        headers=headers,
    )
    fresh = client.patch(
        f"/api/v1/groups/{group.id}",
        json={"expected_version": 2, "name": "Fresh"},
        headers=headers,
    )

    assert reassigned.status_code == 200
    assert stale.status_code == 409
    assert fresh.status_code == 200
    assert fresh.json()["name"] == "Fresh"


def test_concurrent_group_patch_allows_exactly_one_writer(business_api) -> None:
    client, factory = business_api
    admin = add_user(client, factory, "admin")
    group = add_group(factory, admin)
    second_client = TestClient(client.app)
    first_headers = authenticate(client, admin.login)
    second_headers = authenticate(second_client, admin.login)
    barrier = Barrier(2)

    def patch(test_client: TestClient, headers: dict[str, str], name: str) -> int:
        barrier.wait()
        return test_client.patch(
            f"/api/v1/groups/{group.id}",
            json={"expected_version": 1, "name": name},
            headers=headers,
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = [
                executor.submit(patch, client, first_headers, "First"),
                executor.submit(patch, second_client, second_headers, "Second"),
            ]
            statuses = [future.result() for future in outcomes]
    finally:
        second_client.close()

    assert sorted(statuses) == [200, 409]
    with factory() as database:
        persisted = database.get(Group, group.id)
        assert persisted.version == 2
        assert persisted.name in {"First", "Second"}


def test_concurrent_student_patch_allows_exactly_one_writer(business_api) -> None:
    client, factory = business_api
    admin = add_user(client, factory, "admin")
    group = add_group(factory, admin)
    student = add_student(factory, group, "Initial")
    second_client = TestClient(client.app)
    first_headers = authenticate(client, admin.login)
    second_headers = authenticate(second_client, admin.login)
    barrier = Barrier(2)

    def patch(test_client: TestClient, headers: dict[str, str], name: str) -> int:
        barrier.wait()
        return test_client.patch(
            f"/api/v1/students/{student.id}",
            json={"expected_version": 1, "name": name},
            headers=headers,
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = [
                executor.submit(patch, client, first_headers, "First"),
                executor.submit(patch, second_client, second_headers, "Second"),
            ]
            statuses = [future.result() for future in outcomes]
    finally:
        second_client.close()

    assert sorted(statuses) == [200, 409]
    with factory() as database:
        persisted = database.get(Student, student.id)
        assert persisted.version == 2
        assert persisted.name in {"First", "Second"}


def test_student_creation_scope_list_contract_and_validation(business_api) -> None:
    client, factory = business_api
    own_admin = add_user(client, factory, "own")
    other_admin = add_user(client, factory, "other")
    student_user = add_user(client, factory, "student", role=UserRole.STUDENT)
    own_group = add_group(factory, own_admin)
    other_group = add_group(factory, other_admin)
    own_profile = add_student(factory, own_group, "Own", user=student_user)
    own_headers = authenticate(client, own_admin.login)

    foreign_create = client.post(
        f"/api/v1/groups/{other_group.id}/students",
        json={"name": "Нельзя"},
        headers=own_headers,
    )
    listing = client.get(f"/api/v1/groups/{other_group.id}/students", headers=own_headers)
    invalid_url = client.post(
        f"/api/v1/groups/{own_group.id}/students",
        json={"name": "X", "links": {"portfolio": "javascript:alert(1)"}},
        headers=own_headers,
    )
    student_headers = authenticate(client, student_user.login)
    student_list = client.get(f"/api/v1/groups/{own_group.id}/students", headers=student_headers)
    student_patch = client.patch(
        f"/api/v1/students/{own_profile.id}",
        json={"expected_version": 1, "name": "Нельзя"},
        headers=student_headers,
    )
    foreign_profile = add_student(factory, other_group, "Foreign")
    own_headers = authenticate(client, own_admin.login)
    foreign_patch = client.patch(
        f"/api/v1/students/{foreign_profile.id}",
        json={"expected_version": 1, "name": "Нельзя"},
        headers=own_headers,
    )
    server_managed_patch = client.patch(
        f"/api/v1/students/{own_profile.id}",
        json={"expected_version": 1, "group_id": other_group.id, "user_id": own_admin.id},
        headers=own_headers,
    )

    assert foreign_create.status_code == 403
    assert listing.status_code == 200
    assert invalid_url.status_code == 422
    assert student_list.status_code == 403
    assert student_patch.status_code == 403
    assert foreign_patch.status_code == 403
    assert server_managed_patch.status_code == 422


def test_owner_creates_student_and_student_list_paginates_stably(business_api) -> None:
    client, factory = business_api
    owner = add_user(client, factory, "owner", owner=True)
    curator = add_user(client, factory, "curator")
    group = add_group(factory, curator)
    headers = authenticate(client, owner.login)

    created = client.post(
        f"/api/v1/groups/{group.id}/students",
        json={"name": "Создана владельцем"},
        headers=headers,
    )
    for index in range(2):
        add_student(factory, group, f"Профиль {index}")
    first_page = client.get(f"/api/v1/groups/{group.id}/students?limit=2", headers=headers)
    second_page = client.get(
        f"/api/v1/groups/{group.id}/students",
        params={"limit": 2, "cursor": first_page.json()["next_cursor"]},
        headers=headers,
    )

    assert created.status_code == 201
    assert created.json()["group_id"] == group.id
    assert len(first_page.json()["items"]) == 2
    assert len(second_page.json()["items"]) == 1
    assert set(item["id"] for item in first_page.json()["items"]).isdisjoint(
        item["id"] for item in second_page.json()["items"]
    )


def test_student_archive_preserves_account_and_access_in_archived_group(business_api) -> None:
    client, factory = business_api
    admin = add_user(client, factory, "admin")
    student_user = add_user(client, factory, "student", role=UserRole.STUDENT)
    group = add_group(factory, admin)
    student = add_student(factory, group, "Ученица", user=student_user)
    admin_headers = authenticate(client, admin.login)

    archived_student = client.post(
        f"/api/v1/students/{student.id}/archive",
        json={"expected_version": 1},
        headers=admin_headers,
    )
    archived_group = client.post(
        f"/api/v1/groups/{group.id}/archive",
        json={"expected_version": 1},
        headers=admin_headers,
    )
    student_headers = authenticate(client, student_user.login)
    profile = client.get(f"/api/v1/students/{student.id}", headers=student_headers)
    own_group = client.get(f"/api/v1/groups/{group.id}", headers=student_headers)
    admin_headers = authenticate(client, admin.login)
    restored_student = client.post(
        f"/api/v1/students/{student.id}/restore",
        json={"expected_version": 2},
        headers=admin_headers,
    )

    assert archived_student.status_code == 200
    assert archived_group.status_code == 200
    assert profile.status_code == 200
    assert own_group.status_code == 200
    assert restored_student.status_code == 200
    assert restored_student.json()["archived_at"] is None
    with factory() as database:
        persisted = database.get(Student, student.id)
        assert persisted.user_id == student_user.id
        assert database.get(User, student_user.id).is_active is True


def test_cannot_create_student_in_archived_group(business_api) -> None:
    client, factory = business_api
    admin = add_user(client, factory, "admin")
    group = add_group(factory, admin)
    headers = authenticate(client, admin.login)
    assert (
        client.post(
            f"/api/v1/groups/{group.id}/archive",
            json={"expected_version": 1},
            headers=headers,
        ).status_code
        == 200
    )

    response = client.post(
        f"/api/v1/groups/{group.id}/students",
        json={"name": "Поздняя ученица"},
        headers=headers,
    )

    assert response.status_code == 409
    with factory() as database:
        assert database.scalar(select(Student).where(Student.name == "Поздняя ученица")) is None


def test_student_creation_and_group_archive_are_serializable(business_api) -> None:
    client, factory = business_api
    admin = add_user(client, factory, "admin")
    group = add_group(factory, admin)
    second_client = TestClient(client.app)
    create_headers = authenticate(client, admin.login)
    archive_headers = authenticate(second_client, admin.login)
    barrier = Barrier(2)

    def create() -> int:
        barrier.wait()
        return client.post(
            f"/api/v1/groups/{group.id}/students",
            json={"name": "Concurrent"},
            headers=create_headers,
        ).status_code

    def archive() -> int:
        barrier.wait()
        return second_client.post(
            f"/api/v1/groups/{group.id}/archive",
            json={"expected_version": 1},
            headers=archive_headers,
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            create_future = executor.submit(create)
            archive_future = executor.submit(archive)
            create_status = create_future.result()
            archive_status = archive_future.result()
    finally:
        second_client.close()

    assert archive_status == 200
    assert create_status in {201, 409}
    with factory() as database:
        assert database.get(Group, group.id).status is GroupStatus.ARCHIVED
        created_count = len(
            list(database.scalars(select(Student).where(Student.name == "Concurrent")))
        )
        assert created_count == (1 if create_status == 201 else 0)


def test_failed_audit_commit_rolls_back_group_update(business_api, monkeypatch) -> None:
    client, factory = business_api
    admin = add_user(client, factory, "admin")
    group = add_group(factory, admin, "До изменения")
    headers = authenticate(client, admin.login)

    def invalid_audit(database: Session, **_: object) -> None:
        database.add(
            AuditEvent(
                id="invalid-event",
                actor_user_id="missing-user",
                target_group_id=group.id,
                action="group_updated",
            )
        )

    monkeypatch.setattr("app.modules.groups.service.record_audit", invalid_audit)
    response = client.patch(
        f"/api/v1/groups/{group.id}",
        json={"expected_version": 1, "name": "После изменения"},
        headers=headers,
    )

    assert response.status_code == 409
    with factory() as database:
        persisted = database.get(Group, group.id)
        assert persisted.name == "До изменения"
        assert persisted.version == 1
        assert database.get(AuditEvent, "invalid-event") is None
