from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.errors import ApiError
from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine, get_db
from app.main import create_app
from app.modules.auth.authorization import can_update_group
from app.modules.auth.models import AuthSession
from app.modules.auth.passwords import PasswordManager
from app.modules.groups.models import Group, GroupStatus
from app.modules.students.models import Student
from app.modules.users.audit import AuditAction, AuditEvent
from app.modules.users.models import User, UserRole
from app.modules.users.service import assign_group

PASSWORD = "correct horse battery staple"

ADMIN_ENDPOINT_CASES = (
    ("POST", "/api/v1/admin/curators", {"login": "matrix.curator"}),
    ("GET", "/api/v1/admin/curators", None),
    ("GET", "/api/v1/admin/curators/missing-user", None),
    ("POST", "/api/v1/admin/curators/missing-user/deactivate", None),
    (
        "POST",
        "/api/v1/admin/students/missing-student/account",
        {"login": "matrix.student"},
    ),
    ("GET", "/api/v1/admin/students/missing-student/account", None),
    ("POST", "/api/v1/admin/students/missing-student/deactivate-account", None),
    ("POST", "/api/v1/admin/users/missing-user/reset-password", None),
    (
        "POST",
        "/api/v1/admin/groups/missing-group/reassign-curator",
        {"curator_id": "missing-user"},
    ),
    (
        "POST",
        "/api/v1/admin/curators/missing-user/offboard",
        {"successor_curator_id": "missing-user"},
    ),
    ("POST", "/api/v1/admin/curators/missing-user/transfer-ownership", None),
)

ADMIN_OPENAPI_OPERATIONS = {
    ("post", "/api/v1/admin/curators"),
    ("get", "/api/v1/admin/curators"),
    ("get", "/api/v1/admin/curators/{user_id}"),
    ("post", "/api/v1/admin/curators/{user_id}/deactivate"),
    ("post", "/api/v1/admin/students/{student_id}/account"),
    ("get", "/api/v1/admin/students/{student_id}/account"),
    ("post", "/api/v1/admin/students/{student_id}/deactivate-account"),
    ("post", "/api/v1/admin/users/{user_id}/reset-password"),
    ("post", "/api/v1/admin/groups/{group_id}/reassign-curator"),
    ("post", "/api/v1/admin/curators/{user_id}/offboard"),
    ("post", "/api/v1/admin/curators/{user_id}/transfer-ownership"),
}


@pytest.fixture
def user_management_context() -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    database_path = Path(f".user-management-{uuid4()}.db").resolve()
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
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
        with factory() as database_session:
            yield database_session

    application.dependency_overrides[get_db] = override_db
    with TestClient(application) as client:
        yield client, factory
    Base.metadata.drop_all(engine)
    engine.dispose()
    database_path.unlink(missing_ok=True)


def add_user(
    client: TestClient,
    factory: sessionmaker[Session],
    login: str,
    *,
    role: UserRole = UserRole.ADMIN,
    owner: bool = False,
) -> User:
    manager: PasswordManager = client.app.state.password_manager
    user = User(
        login=login,
        role=role,
        password_hash=manager.hash(PASSWORD),
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


def call_admin_endpoint(
    client: TestClient,
    method: str,
    path: str,
    payload: dict[str, str] | None,
    headers: dict[str, str] | None = None,
):
    request_arguments: dict[str, object] = {"headers": headers or {}}
    if payload is not None:
        request_arguments["json"] = payload
    return client.request(method, path, **request_arguments)


def test_openapi_contains_exact_user_management_operations_and_creation_statuses(
    user_management_context,
) -> None:
    client, _ = user_management_context

    schema = client.app.openapi()
    actual_operations = {
        (method, path)
        for path, path_item in schema["paths"].items()
        if path.startswith("/api/v1/admin/")
        for method in path_item
        if method in {"get", "post", "put", "patch", "delete"}
    }

    assert actual_operations == ADMIN_OPENAPI_OPERATIONS
    assert "201" in schema["paths"]["/api/v1/admin/curators"]["post"]["responses"]
    assert (
        "201" in schema["paths"]["/api/v1/admin/students/{student_id}/account"]["post"]["responses"]
    )


@pytest.mark.parametrize(("method", "path", "payload"), ADMIN_ENDPOINT_CASES)
def test_every_admin_endpoint_rejects_missing_authentication(
    user_management_context,
    method: str,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    client, _ = user_management_context

    response = call_admin_endpoint(client, method, path, payload)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize(("method", "path", "payload"), ADMIN_ENDPOINT_CASES)
def test_every_admin_endpoint_rejects_student_actor(
    user_management_context,
    method: str,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    client, factory = user_management_context
    student = add_user(client, factory, "matrix.student", role=UserRole.STUDENT)
    headers = authenticate(client, student.login)

    response = call_admin_endpoint(client, method, path, payload, headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize(("method", "path", "payload"), ADMIN_ENDPOINT_CASES)
def test_every_admin_endpoint_rejects_inactive_actor(
    user_management_context,
    method: str,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    client, factory = user_management_context
    actor = add_user(client, factory, "inactive.matrix")
    headers = authenticate(client, actor.login)
    with factory.begin() as database:
        persisted = database.get(User, actor.id)
        persisted.is_active = False
        persisted.deactivated_at = datetime(2026, 1, 1)

    response = call_admin_endpoint(client, method, path, payload, headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize(
    ("method", "path", "payload", "expected_status"),
    tuple(
        (*case, 200 if case[1] == "/api/v1/admin/curators" else 404)
        for case in ADMIN_ENDPOINT_CASES
        if case[1]
        not in {
            "/api/v1/admin/curators",
            "/api/v1/admin/curators/missing-user",
            "/api/v1/admin/curators/missing-user/deactivate",
            "/api/v1/admin/groups/missing-group/reassign-curator",
            "/api/v1/admin/curators/missing-user/offboard",
            "/api/v1/admin/curators/missing-user/transfer-ownership",
        }
    )
    + (
        ("GET", "/api/v1/admin/curators", None, 200),
        ("POST", "/api/v1/admin/curators", {"login": "forbidden.curator"}, 403),
        ("GET", "/api/v1/admin/curators/missing-user", None, 403),
        ("POST", "/api/v1/admin/curators/missing-user/deactivate", None, 403),
        (
            "POST",
            "/api/v1/admin/groups/missing-group/reassign-curator",
            {"curator_id": "missing-user"},
            403,
        ),
        (
            "POST",
            "/api/v1/admin/curators/missing-user/offboard",
            {"successor_curator_id": "missing-user"},
            403,
        ),
        ("POST", "/api/v1/admin/curators/missing-user/transfer-ownership", None, 403),
    ),
)
def test_ordinary_admin_endpoint_matrix(
    user_management_context,
    method: str,
    path: str,
    payload: dict[str, str] | None,
    expected_status: int,
) -> None:
    client, factory = user_management_context
    actor = add_user(client, factory, "matrix.admin")
    headers = authenticate(client, actor.login)

    response = call_admin_endpoint(client, method, path, payload, headers)

    assert response.status_code == expected_status


@pytest.mark.parametrize(("method", "path", "payload"), ADMIN_ENDPOINT_CASES[2:])
def test_owner_gets_not_found_for_tampered_object_identifiers(
    user_management_context,
    method: str,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "matrix.owner", owner=True)
    headers = authenticate(client, owner.login)

    response = call_admin_endpoint(client, method, path, payload, headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_mutation_schemas_reject_mass_assignment_fields(user_management_context) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    curator = add_user(client, factory, "curator")
    successor = add_user(client, factory, "successor")
    group, student = add_group_and_student(factory, curator)
    headers = authenticate(client, owner.login)

    student_response = client.post(
        f"/api/v1/admin/students/{student.id}/account",
        json={"login": "mass.assignment.student", "is_owner": True},
        headers=headers,
    )
    reassign_response = client.post(
        f"/api/v1/admin/groups/{group.id}/reassign-curator",
        json={"curator_id": successor.id, "role": "owner"},
        headers=headers,
    )
    offboard_response = client.post(
        f"/api/v1/admin/curators/{curator.id}/offboard",
        json={"successor_curator_id": successor.id, "is_owner": True},
        headers=headers,
    )

    assert student_response.status_code == 422
    assert reassign_response.status_code == 422
    assert offboard_response.status_code == 422
    with factory() as database:
        assert database.get(Student, student.id).user_id is None
        assert database.get(Group, group.id).curator_id == curator.id
        assert database.get(User, curator.id).is_active is True


def add_group_and_student(
    factory: sessionmaker[Session], curator: User, *, name: str = "Student"
) -> tuple[Group, Student]:
    with factory.begin() as database:
        group = Group(
            name="Group",
            curator_id=curator.id,
            starts_at=date(2026, 1, 1),
            status=GroupStatus.ACTIVE,
        )
        database.add(group)
        database.flush()
        student = Student(group_id=group.id, name=name, notes="keep me")
        database.add(student)
    return group, student


def test_owner_creates_curator_with_one_time_temporary_password(
    user_management_context,
) -> None:
    client, factory = user_management_context
    add_user(client, factory, "owner", owner=True)
    headers = authenticate(client, "owner")

    response = client.post(
        "/api/v1/admin/curators",
        json={"login": " New.Curator "},
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["login"] == "new.curator"
    assert body["user"]["role"] == "admin"
    assert body["user"]["is_owner"] is False
    assert body["user"]["is_active"] is True
    assert body["temporary_password"] not in str(body["user"])
    with factory() as database:
        created = database.scalar(select(User).where(User.login == "new.curator"))
        assert created is not None
        assert created.must_change_password is True
        assert created.password_hash.startswith("$argon2id$")
        assert body["temporary_password"] not in created.password_hash
    client.cookies.clear()
    login_response = client.post(
        "/api/v1/auth/login",
        json={"login": "new.curator", "password": body["temporary_password"]},
        headers={"Origin": "http://testserver"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["must_change_password"] is True
    change_response = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": body["temporary_password"],
            "new_password": "a new permanent password",
        },
        headers={
            "Origin": "http://testserver",
            "X-CSRF-Token": client.cookies.get("kuratorskaya_csrf"),
        },
    )
    assert change_response.status_code == 204
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"login": "new.curator", "password": body["temporary_password"]},
            headers={"Origin": "http://testserver"},
        ).status_code
        == 401
    )


def test_assigned_curator_creates_student_account_without_changing_profile(
    user_management_context,
) -> None:
    client, factory = user_management_context
    curator = add_user(client, factory, "curator")
    group, student = add_group_and_student(factory, curator, name="Test Student")
    headers = authenticate(client, "curator")

    response = client.post(
        f"/api/v1/admin/students/{student.id}/account",
        json={"login": "student.login"},
        headers=headers,
    )

    assert response.status_code == 201
    with factory() as database:
        persisted = database.get(Student, student.id)
        assert persisted.group_id == group.id
        assert persisted.notes == "keep me"
        assert persisted.user_id == response.json()["user"]["id"]
        assert persisted.version == 2
        account = database.get(User, persisted.user_id)
        assert account.role is UserRole.STUDENT
        assert account.must_change_password is True


def test_reset_password_revokes_sessions_and_never_returns_secrets_in_audit(
    user_management_context,
) -> None:
    client, factory = user_management_context
    add_user(client, factory, "owner", owner=True)
    target = add_user(client, factory, "target")
    with factory.begin() as database:
        database.add(
            AuthSession(
                user_id=target.id,
                token_hash="a" * 64,
                csrf_token_hash="b" * 64,
                created_at=datetime(2026, 1, 1),
                last_activity_at=datetime(2026, 1, 1),
                absolute_expires_at=datetime(2027, 1, 1),
            )
        )
    headers = authenticate(client, "owner")

    response = client.post(f"/api/v1/admin/users/{target.id}/reset-password", headers=headers)

    assert response.status_code == 200
    assert response.json()["temporary_password"]
    with factory() as database:
        account = database.get(User, target.id)
        auth_session = database.scalar(select(AuthSession).where(AuthSession.user_id == target.id))
        assert account.must_change_password is True
        assert auth_session.revoked_at is not None


def test_curator_creation_requires_owner_and_csrf(user_management_context) -> None:
    client, factory = user_management_context
    add_user(client, factory, "admin")
    headers = authenticate(client, "admin")

    forbidden = client.post(
        "/api/v1/admin/curators", json={"login": "other.admin"}, headers=headers
    )
    missing_csrf = client.post(
        "/api/v1/admin/curators",
        json={"login": "other.admin"},
        headers={"Origin": "http://testserver"},
    )

    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "forbidden"
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["error"]["code"] == "invalid_csrf_token"


def test_normalized_duplicate_login_returns_conflict(user_management_context) -> None:
    client, factory = user_management_context
    add_user(client, factory, "owner", owner=True)
    add_user(client, factory, "existing.login")
    headers = authenticate(client, "owner")

    response = client.post(
        "/api/v1/admin/curators",
        json={"login": " EXISTING.LOGIN "},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "login_conflict"


def test_curator_cannot_create_or_reset_foreign_student_account(
    user_management_context,
) -> None:
    client, factory = user_management_context
    actor = add_user(client, factory, "actor")
    other = add_user(client, factory, "other")
    _, foreign_student = add_group_and_student(factory, other)
    foreign_account = add_user(client, factory, "foreign.student", role=UserRole.STUDENT)
    with factory.begin() as database:
        database.get(Student, foreign_student.id).user_id = foreign_account.id
    headers = authenticate(client, actor.login)

    create_response = client.post(
        f"/api/v1/admin/students/{foreign_student.id}/account",
        json={"login": "hijacked.student"},
        headers=headers,
    )
    reset_response = client.post(
        f"/api/v1/admin/users/{foreign_account.id}/reset-password", headers=headers
    )

    assert create_response.status_code == 404
    assert reset_response.status_code == 404


def test_student_cannot_use_admin_endpoints(user_management_context) -> None:
    client, factory = user_management_context
    student_user = add_user(client, factory, "student", role=UserRole.STUDENT)
    headers = authenticate(client, student_user.login)

    response = client.get("/api/v1/admin/curators", headers=headers)

    assert response.status_code == 403


def test_student_account_cannot_be_linked_twice(user_management_context) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    _, student = add_group_and_student(factory, owner)
    headers = authenticate(client, owner.login)
    first = client.post(
        f"/api/v1/admin/students/{student.id}/account",
        json={"login": "student.one"},
        headers=headers,
    )

    second = client.post(
        f"/api/v1/admin/students/{student.id}/account",
        json={"login": "student.two"},
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409
    with factory() as database:
        assert database.scalar(select(User).where(User.login == "student.two")) is None


def test_owner_reassigns_group_and_offboards_curator_atomically(
    user_management_context,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    departing = add_user(client, factory, "departing")
    successor = add_user(client, factory, "successor")
    group_one, _ = add_group_and_student(factory, departing, name="One")
    group_two, _ = add_group_and_student(factory, departing, name="Two")
    authenticate(client, departing.login)
    headers = authenticate(client, owner.login)

    response = client.post(
        f"/api/v1/admin/curators/{departing.id}/offboard",
        json={"successor_curator_id": successor.id},
        headers=headers,
    )

    assert response.status_code == 200
    assert set(response.json()["reassigned_group_ids"]) == {group_one.id, group_two.id}
    with factory() as database:
        assert database.get(User, departing.id).is_active is False
        assert {
            database.get(Group, group_one.id).curator_id,
            database.get(Group, group_two.id).curator_id,
        } == {successor.id}
        assert {
            database.get(Group, group_one.id).version,
            database.get(Group, group_two.id).version,
        } == {2}
        actions = list(database.scalars(select(AuditEvent.action)))
        assert actions.count(AuditAction.CURATOR_REASSIGNED) == 2
        assert AuditAction.CURATOR_OFFBOARDED in actions
        departing_sessions = list(
            database.scalars(select(AuthSession).where(AuthSession.user_id == departing.id))
        )
        assert departing_sessions
        assert all(session.revoked_at is not None for session in departing_sessions)


def test_offboarding_rolls_back_when_successor_is_not_active_admin(
    user_management_context,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    departing = add_user(client, factory, "departing")
    invalid = add_user(client, factory, "student", role=UserRole.STUDENT)
    group, _ = add_group_and_student(factory, departing)
    headers = authenticate(client, owner.login)

    response = client.post(
        f"/api/v1/admin/curators/{departing.id}/offboard",
        json={"successor_curator_id": invalid.id},
        headers=headers,
    )

    assert response.status_code == 422
    with factory() as database:
        assert database.get(User, departing.id).is_active is True
        assert database.get(Group, group.id).curator_id == departing.id
        assert database.scalar(select(AuditEvent)) is None


def test_last_owner_cannot_be_deactivated_and_can_transfer_ownership(
    user_management_context,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    successor = add_user(client, factory, "successor")
    headers = authenticate(client, owner.login)

    blocked = client.post(f"/api/v1/admin/curators/{owner.id}/deactivate", headers=headers)
    transferred = client.post(
        f"/api/v1/admin/curators/{successor.id}/transfer-ownership", headers=headers
    )

    assert blocked.status_code == 409
    assert transferred.status_code == 200
    with factory() as database:
        assert database.get(User, owner.id).is_owner is False
        assert database.get(User, successor.id).is_owner is True
        event = database.scalar(
            select(AuditEvent).where(AuditEvent.action == AuditAction.OWNER_TRANSFERRED)
        )
        assert event.actor_user_id == owner.id
        assert event.target_user_id == successor.id
        assert event.details == {"previous_owner_id": owner.id}


def test_owner_cannot_transfer_ownership_to_self_or_invalid_account(
    user_management_context,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    inactive_admin = add_user(client, factory, "inactive.admin")
    student = add_user(client, factory, "student", role=UserRole.STUDENT)
    with factory.begin() as database:
        inactive = database.get(User, inactive_admin.id)
        inactive.is_active = False
        inactive.deactivated_at = datetime(2026, 1, 1)
    headers = authenticate(client, owner.login)

    self_transfer = client.post(
        f"/api/v1/admin/curators/{owner.id}/transfer-ownership", headers=headers
    )
    inactive_transfer = client.post(
        f"/api/v1/admin/curators/{inactive_admin.id}/transfer-ownership", headers=headers
    )
    student_transfer = client.post(
        f"/api/v1/admin/curators/{student.id}/transfer-ownership", headers=headers
    )

    assert self_transfer.status_code == 422
    assert inactive_transfer.status_code == 422
    assert student_transfer.status_code == 404
    with factory() as database:
        assert database.get(User, owner.id).is_owner is True
        assert database.get(User, inactive_admin.id).is_owner is False
        assert (
            database.scalar(
                select(AuditEvent).where(AuditEvent.action == AuditAction.OWNER_TRANSFERRED)
            )
            is None
        )


def test_reset_password_replaces_previous_password_and_audit_contains_no_secret(
    user_management_context,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    target = add_user(client, factory, "target")
    headers = authenticate(client, owner.login)

    first = client.post(f"/api/v1/admin/users/{target.id}/reset-password", headers=headers)
    second = client.post(f"/api/v1/admin/users/{target.id}/reset-password", headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["temporary_password"] != second.json()["temporary_password"]
    with factory() as database:
        persisted = database.get(User, target.id)
        manager: PasswordManager = client.app.state.password_manager
        assert not manager.verify(first.json()["temporary_password"], persisted.password_hash)
        assert manager.verify(second.json()["temporary_password"], persisted.password_hash)
        events = list(database.scalars(select(AuditEvent)))
        serialized = " ".join(str(event.details) for event in events)
        assert first.json()["temporary_password"] not in serialized
        assert second.json()["temporary_password"] not in serialized


def test_temporary_credentials_are_not_written_to_application_logs(
    user_management_context,
    caplog,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    headers = authenticate(client, owner.login)
    caplog.clear()

    created = client.post(
        "/api/v1/admin/curators",
        json={"login": "no.log.secret"},
        headers=headers,
    )
    temporary_password = created.json()["temporary_password"]
    reset = client.post(
        f"/api/v1/admin/users/{created.json()['user']['id']}/reset-password",
        headers=headers,
    )
    reset_password_value = reset.json()["temporary_password"]

    assert created.status_code == 201
    assert reset.status_code == 200
    assert temporary_password not in caplog.text
    assert reset_password_value not in caplog.text


def test_failed_duplicate_creation_does_not_expose_generated_temporary_password(
    user_management_context,
    monkeypatch,
    caplog,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    add_user(client, factory, "duplicate.login")
    headers = authenticate(client, owner.login)
    generated_secret = "KnownTemporarySecret42"
    monkeypatch.setattr(
        "app.modules.users.service.generate_temporary_password",
        lambda: generated_secret,
    )
    caplog.clear()

    response = client.post(
        "/api/v1/admin/curators",
        json={"login": " DUPLICATE.LOGIN "},
        headers=headers,
    )

    assert response.status_code == 409
    assert generated_secret not in response.text
    assert generated_secret not in caplog.text
    with factory() as database:
        assert database.scalar(select(AuditEvent)) is None
        assert all(
            generated_secret not in password_hash
            for password_hash in database.scalars(select(User.password_hash))
        )


def test_reset_password_commit_failure_rolls_back_hash_sessions_and_audit(
    user_management_context,
    monkeypatch,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    target = add_user(client, factory, "target")
    with factory.begin() as database:
        database.add(
            AuthSession(
                user_id=target.id,
                token_hash="c" * 64,
                csrf_token_hash="d" * 64,
                created_at=datetime(2026, 1, 1),
                last_activity_at=datetime(2026, 1, 1),
                absolute_expires_at=datetime(2027, 1, 1),
            )
        )
    headers = authenticate(client, owner.login)
    with factory() as database:
        original_hash = database.get(User, target.id).password_hash

    def fail_commit(_: Session) -> None:
        raise RuntimeError("simulated commit failure")

    with monkeypatch.context() as patcher:
        patcher.setattr(Session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="simulated commit failure"):
            client.post(
                f"/api/v1/admin/users/{target.id}/reset-password",
                headers=headers,
            )

    with factory() as database:
        persisted = database.get(User, target.id)
        target_session = database.scalar(
            select(AuthSession).where(AuthSession.user_id == target.id)
        )
        assert persisted.password_hash == original_hash
        assert persisted.must_change_password is False
        assert target_session.revoked_at is None
        assert database.scalar(select(AuditEvent)) is None


def test_audit_failure_rolls_back_student_link_and_owner_transfer(
    user_management_context,
    monkeypatch,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    successor = add_user(client, factory, "successor")
    _, student = add_group_and_student(factory, owner)
    headers = authenticate(client, owner.login)

    def fail_audit(*_args, **_kwargs) -> None:
        raise RuntimeError("simulated audit failure")

    with monkeypatch.context() as patcher:
        patcher.setattr("app.modules.users.service.record_audit", fail_audit)
        with pytest.raises(RuntimeError, match="simulated audit failure"):
            client.post(
                f"/api/v1/admin/students/{student.id}/account",
                json={"login": "rollback.student"},
                headers=headers,
            )
        with pytest.raises(RuntimeError, match="simulated audit failure"):
            client.post(
                f"/api/v1/admin/curators/{successor.id}/transfer-ownership",
                headers=headers,
            )

    with factory() as database:
        assert database.get(Student, student.id).user_id is None
        assert database.scalar(select(User).where(User.login == "rollback.student")) is None
        assert database.get(User, owner.id).is_owner is True
        assert database.get(User, successor.id).is_owner is False
        assert database.scalar(select(AuditEvent)) is None


def test_curator_gets_safe_list_without_csrf(user_management_context) -> None:
    client, factory = user_management_context
    actor = add_user(client, factory, "actor")
    add_user(client, factory, "other")
    authenticate(client, actor.login)

    response = client.get("/api/v1/admin/curators")

    assert response.status_code == 200
    assert {item["login"] for item in response.json()} == {"actor", "other"}
    assert all("must_change_password" not in item for item in response.json())
    assert all("deactivated_at" not in item for item in response.json())
    serialized = response.text.lower()
    for secret_field in ("password_hash", "session", "csrf", "temporary_password"):
        assert secret_field not in serialized


def test_owner_reads_curator_and_assigned_curator_reads_student_account(
    user_management_context,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    curator = add_user(client, factory, "curator")
    _, student = add_group_and_student(factory, curator)
    owner_headers = authenticate(client, owner.login)
    curator_response = client.get(f"/api/v1/admin/curators/{curator.id}", headers=owner_headers)
    create_response = client.post(
        f"/api/v1/admin/students/{student.id}/account",
        json={"login": "readable.student"},
        headers=owner_headers,
    )
    authenticate(client, curator.login)

    student_response = client.get(f"/api/v1/admin/students/{student.id}/account")

    assert curator_response.status_code == 200
    assert curator_response.json()["id"] == curator.id
    assert create_response.status_code == 201
    assert student_response.status_code == 200
    assert student_response.json()["user"]["login"] == "readable.student"
    assert "temporary_password" not in student_response.json()


def test_creation_rejects_invalid_login_and_mass_assignment(user_management_context) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    headers = authenticate(client, owner.login)

    invalid = client.post("/api/v1/admin/curators", json={"login": "Не логин"}, headers=headers)
    mass_assignment = client.post(
        "/api/v1/admin/curators",
        json={"login": "new.admin", "is_owner": True, "role": "student"},
        headers=headers,
    )

    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_login"
    assert mass_assignment.status_code == 422
    with factory() as database:
        assert database.scalar(select(User).where(User.login == "new.admin")) is None


def test_owner_can_manage_student_in_another_curators_group(user_management_context) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    curator = add_user(client, factory, "curator")
    _, student = add_group_and_student(factory, curator)
    headers = authenticate(client, owner.login)

    response = client.post(
        f"/api/v1/admin/students/{student.id}/account",
        json={"login": "owner.created.student"},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["user"]["role"] == "student"


def test_group_reassignment_changes_permissions_and_rejects_invalid_curators(
    user_management_context,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    previous = add_user(client, factory, "previous")
    successor = add_user(client, factory, "successor")
    inactive = add_user(client, factory, "inactive")
    student_user = add_user(client, factory, "student", role=UserRole.STUDENT)
    with factory.begin() as database:
        database.get(User, inactive.id).is_active = False
        database.get(User, inactive.id).deactivated_at = datetime(2026, 1, 1)
    group, _ = add_group_and_student(factory, previous)
    headers = authenticate(client, owner.login)

    for invalid_id in (student_user.id, inactive.id):
        invalid = client.post(
            f"/api/v1/admin/groups/{group.id}/reassign-curator",
            json={"curator_id": invalid_id},
            headers=headers,
        )
        assert invalid.status_code == 422

    response = client.post(
        f"/api/v1/admin/groups/{group.id}/reassign-curator",
        json={"curator_id": successor.id},
        headers=headers,
    )

    assert response.status_code == 200
    with factory() as database:
        persisted_group = database.get(Group, group.id)
        assert can_update_group(database.get(User, previous.id), persisted_group) is False
        assert can_update_group(database.get(User, successor.id), persisted_group) is True
        assert persisted_group.version == 2


def test_owner_deactivates_unassigned_curator_and_revokes_sessions(
    user_management_context,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    target = add_user(client, factory, "target")
    authenticate(client, target.login)
    headers = authenticate(client, owner.login)

    response = client.post(f"/api/v1/admin/curators/{target.id}/deactivate", headers=headers)

    assert response.status_code == 200
    with factory() as database:
        persisted = database.get(User, target.id)
        assert persisted.is_active is False
        assert persisted.deactivated_at is not None
        sessions = list(
            database.scalars(select(AuthSession).where(AuthSession.user_id == target.id))
        )
        assert sessions and all(session.revoked_at is not None for session in sessions)


def test_curator_with_groups_requires_offboarding(user_management_context) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    target = add_user(client, factory, "target")
    group, _ = add_group_and_student(factory, target)
    headers = authenticate(client, owner.login)

    response = client.post(f"/api/v1/admin/curators/{target.id}/deactivate", headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "curator_has_groups"
    with factory() as database:
        assert database.get(User, target.id).is_active is True
        assert database.get(Group, group.id).curator_id == target.id


def test_student_account_deactivation_preserves_profile_and_history(
    user_management_context,
) -> None:
    client, factory = user_management_context
    curator = add_user(client, factory, "curator")
    _, student = add_group_and_student(factory, curator)
    headers = authenticate(client, curator.login)
    created = client.post(
        f"/api/v1/admin/students/{student.id}/account",
        json={"login": "student.account"},
        headers=headers,
    )
    account_id = created.json()["user"]["id"]

    response = client.post(
        f"/api/v1/admin/students/{student.id}/deactivate-account", headers=headers
    )

    assert response.status_code == 200
    with factory() as database:
        persisted_student = database.get(Student, student.id)
        assert persisted_student.user_id == account_id
        assert persisted_student.notes == "keep me"
        assert database.get(User, account_id).is_active is False
        assert database.scalar(
            select(AuditEvent).where(
                AuditEvent.action == AuditAction.USER_DEACTIVATED,
                AuditEvent.target_user_id == account_id,
            )
        )


def test_expired_session_cannot_access_admin_api(user_management_context) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    authenticate(client, owner.login)
    with factory.begin() as database:
        auth_session = database.scalar(select(AuthSession).where(AuthSession.user_id == owner.id))
        auth_session.absolute_expires_at = datetime(2000, 1, 1)

    response = client.get("/api/v1/admin/curators")

    assert response.status_code == 401


def test_concurrent_curator_creation_allows_only_one_normalized_login(
    user_management_context,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    barrier = Barrier(2)

    def create(login_value: str) -> int:
        with TestClient(client.app) as worker:
            headers = authenticate(worker, owner.login)
            barrier.wait()
            return worker.post(
                "/api/v1/admin/curators",
                json={"login": login_value},
                headers=headers,
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(create, ("Concurrent.User", " concurrent.user ")))

    assert sorted(statuses) == [201, 409]
    with factory() as database:
        assert (
            database.scalar(select(User).where(User.normalized_login == "concurrent.user"))
            is not None
        )
        assert (
            len(
                list(
                    database.scalars(
                        select(AuditEvent).where(AuditEvent.action == AuditAction.CURATOR_CREATED)
                    )
                )
            )
            == 1
        )


def test_concurrent_student_account_linking_leaves_one_account_and_one_audit(
    user_management_context,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    _, student = add_group_and_student(factory, owner)
    barrier = Barrier(2)

    def create(login_value: str) -> int:
        with TestClient(client.app) as worker:
            headers = authenticate(worker, owner.login)
            barrier.wait()
            return worker.post(
                f"/api/v1/admin/students/{student.id}/account",
                json={"login": login_value},
                headers=headers,
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(create, ("student.concurrent.one", "student.concurrent.two")))

    assert sorted(statuses) == [201, 409]
    with factory() as database:
        persisted = database.get(Student, student.id)
        assert persisted.user_id is not None
        linked_user = database.get(User, persisted.user_id)
        assert linked_user.login in {"student.concurrent.one", "student.concurrent.two"}
        created_logins = list(
            database.scalars(
                select(User.login).where(
                    User.login.in_({"student.concurrent.one", "student.concurrent.two"})
                )
            )
        )
        assert created_logins == [linked_user.login]
        assert (
            len(
                list(
                    database.scalars(
                        select(AuditEvent).where(
                            AuditEvent.action == AuditAction.STUDENT_ACCOUNT_CREATED
                        )
                    )
                )
            )
            == 1
        )


def test_concurrent_offboarding_and_reassignment_preserve_responsible_curator(
    user_management_context,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    departing = add_user(client, factory, "departing")
    offboard_successor = add_user(client, factory, "offboard.successor")
    direct_successor = add_user(client, factory, "direct.successor")
    group, _ = add_group_and_student(factory, departing)
    barrier = Barrier(2)

    def offboard() -> int:
        with TestClient(client.app) as worker:
            headers = authenticate(worker, owner.login)
            barrier.wait()
            return worker.post(
                f"/api/v1/admin/curators/{departing.id}/offboard",
                json={"successor_curator_id": offboard_successor.id},
                headers=headers,
            ).status_code

    def reassign() -> int:
        with TestClient(client.app) as worker:
            headers = authenticate(worker, owner.login)
            barrier.wait()
            return worker.post(
                f"/api/v1/admin/groups/{group.id}/reassign-curator",
                json={"curator_id": direct_successor.id},
                headers=headers,
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        offboard_future = executor.submit(offboard)
        reassign_future = executor.submit(reassign)
        statuses = [offboard_future.result(), reassign_future.result()]

    assert all(status in {200, 409} for status in statuses)
    with factory() as database:
        persisted_group = database.get(Group, group.id)
        persisted_curator = database.get(User, persisted_group.curator_id)
        assert persisted_curator.is_active is True
        if database.get(User, departing.id).is_active is False:
            assert persisted_group.curator_id != departing.id


def test_stale_owner_reassignment_cannot_overwrite_newer_assignment(
    user_management_context,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    previous = add_user(client, factory, "previous")
    first_successor = add_user(client, factory, "first.successor")
    stale_successor = add_user(client, factory, "stale.successor")
    group, _ = add_group_and_student(factory, previous)

    with factory() as first_database, factory() as stale_database:
        first_actor = first_database.get(User, owner.id)
        stale_actor = stale_database.get(User, owner.id)
        first_group = first_database.get(Group, group.id)
        stale_group = stale_database.get(Group, group.id)
        first_database.get(User, first_successor.id)
        stale_database.get(User, stale_successor.id)
        assert first_group.version == stale_group.version == 1

        assign_group(first_database, first_actor, group.id, first_successor.id)
        first_database.commit()

        with pytest.raises(ApiError) as conflict:
            assign_group(stale_database, stale_actor, group.id, stale_successor.id)

        assert conflict.value.status_code == 409
        assert conflict.value.code == "version_conflict"
        stale_database.rollback()

    with factory() as database:
        persisted = database.get(Group, group.id)
        assert persisted.curator_id == first_successor.id
        assert persisted.version == 2
        events = list(
            database.scalars(
                select(AuditEvent).where(AuditEvent.action == AuditAction.CURATOR_REASSIGNED)
            )
        )
        assert len(events) == 1


def test_concurrent_password_resets_leave_only_latest_credential_valid(
    user_management_context,
) -> None:
    client, factory = user_management_context
    owner = add_user(client, factory, "owner", owner=True)
    target = add_user(client, factory, "target")
    barrier = Barrier(2)

    def reset() -> tuple[int, str | None]:
        with TestClient(client.app) as worker:
            headers = authenticate(worker, owner.login)
            barrier.wait()
            response = worker.post(
                f"/api/v1/admin/users/{target.id}/reset-password", headers=headers
            )
            return response.status_code, response.json().get("temporary_password")

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: reset(), range(2)))

    assert [status for status, _ in outcomes] == [200, 200]
    passwords = [password for _, password in outcomes if password is not None]
    assert len(passwords) == 2
    with factory() as database:
        password_hash = database.get(User, target.id).password_hash
        manager: PasswordManager = client.app.state.password_manager
        assert sum(manager.verify(password, password_hash) for password in passwords) == 1
        assert (
            len(
                list(
                    database.scalars(
                        select(AuditEvent).where(AuditEvent.action == AuditAction.PASSWORD_RESET)
                    )
                )
            )
            == 2
        )
