from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine, get_db
from app.main import create_app
from app.modules.auth.passwords import PasswordManager
from app.modules.knowledge import service as knowledge_service
from app.modules.knowledge.models import KnowledgeDocument
from app.modules.knowledge.sanitizer import sanitize_knowledge_html
from app.modules.users.audit import AuditAction, AuditEvent
from app.modules.users.models import User, UserRole

PASSWORD = "correct horse battery staple"


@pytest.fixture
def knowledge_api(tmp_path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'knowledge-api.db').as_posix()}"
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
    active: bool = True,
    must_change_password: bool = False,
) -> User:
    manager: PasswordManager = client.app.state.password_manager
    user = User(
        login=login,
        role=role,
        password_hash=manager.hash(PASSWORD),
        is_active=active,
        must_change_password=must_change_password,
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


def document_payload(title: str = "Синтетический промпт") -> dict[str, object]:
    return {
        "kind": "prompt",
        "title": title,
        "category": "Другие",
        "html": "<p>Безопасный синтетический текст</p>",
        "position": 0,
    }


def create_document(
    client: TestClient, headers: dict[str, str], title: str = "Синтетический промпт"
):
    response = client.post(
        "/api/v1/knowledge/documents",
        json=document_payload(title),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_crud_archive_restore_and_audit_without_content(knowledge_api) -> None:
    client, factory = knowledge_api
    admin = add_user(client, factory, "knowledge.admin")
    headers = authenticate(client, admin.login)

    created = create_document(client, headers)
    assert created["plain_text"] == "Безопасный синтетический текст"
    assert created["version"] == 1
    assert created["archived_at"] is None

    detail = client.get(f"/api/v1/knowledge/documents/{created['id']}", headers=headers)
    updated = client.patch(
        f"/api/v1/knowledge/documents/{created['id']}",
        json={
            "expected_version": 1,
            "title": "Обновлённый материал",
            "html": "<p>Новая версия</p>",
        },
        headers=headers,
    )
    archived = client.post(
        f"/api/v1/knowledge/documents/{created['id']}/archive",
        json={"expected_version": 2},
        headers=headers,
    )
    hidden = client.get("/api/v1/knowledge/documents", headers=headers)
    visible = client.get("/api/v1/knowledge/documents?include_archived=true", headers=headers)
    restored = client.post(
        f"/api/v1/knowledge/documents/{created['id']}/restore",
        json={"expected_version": 3},
        headers=headers,
    )

    assert detail.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["plain_text"] == "Новая версия"
    assert updated.json()["version"] == 2
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert hidden.json()["items"] == []
    assert [item["id"] for item in visible.json()["items"]] == [created["id"]]
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert restored.json()["version"] == 4

    with factory() as database:
        events = list(
            database.scalars(
                select(AuditEvent).where(
                    AuditEvent.action.in_(
                        [
                            AuditAction.KNOWLEDGE_CREATED,
                            AuditAction.KNOWLEDGE_UPDATED,
                            AuditAction.KNOWLEDGE_ARCHIVED,
                            AuditAction.KNOWLEDGE_RESTORED,
                        ]
                    )
                )
            )
        )
    assert {event.action for event in events} == {
        action.value
        for action in (
            AuditAction.KNOWLEDGE_CREATED,
            AuditAction.KNOWLEDGE_UPDATED,
            AuditAction.KNOWLEDGE_ARCHIVED,
            AuditAction.KNOWLEDGE_RESTORED,
        )
    }
    assert all(event.details["document_id"] == created["id"] for event in events)
    assert all(
        "html" not in event.details and "plain_text" not in event.details for event in events
    )
    assert "Новая версия" not in repr([event.details for event in events])


def test_server_sanitizes_stored_html_and_generates_plain_text(knowledge_api) -> None:
    client, factory = knowledge_api
    admin = add_user(client, factory, "sanitizer.admin")
    headers = authenticate(client, admin.login)
    payload = document_payload("Проверка HTML")
    payload["html"] = (
        '<p>Привет<script>alert("xss")</script>'
        '<a href="javascript:alert(1)" onclick="evil()">опасная ссылка</a>'
        '<a href="https://safe.example/path" target="_blank">безопасная ссылка</a>'
        '<img src="data:image/png;base64,AAAA" onerror="evil()"></p>'
    )

    response = client.post("/api/v1/knowledge/documents", json=payload, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert "script" not in body["html"].lower()
    assert "alert" not in body["html"].lower()
    assert "onclick" not in body["html"].lower()
    assert "javascript:" not in body["html"].lower()
    assert "data:image" not in body["html"].lower()
    assert "<img" not in body["html"].lower()
    assert 'href="https://safe.example/path"' in body["html"]
    assert 'rel="noopener noreferrer"' in body["html"]
    assert body["plain_text"] == "Привет опасная ссылка безопасная ссылка"


def test_sanitizer_preserves_only_allowlisted_structure_and_attributes() -> None:
    sanitized, plain_text = sanitize_knowledge_html(
        '<h2 style="color:red">Раздел</h2><script/>'
        '<table class="layout"><tr><td colspan="2" rowspan="99">Ячейка</td></tr></table>'
        '<a href="/safe" title="Подсказка" target="_blank">Ссылка</a><br/>'
    )

    assert sanitized == (
        "<h2>Раздел</h2>"
        '<table><tr><td colspan="2">Ячейка</td></tr></table>'
        '<a href="/safe" title="Подсказка" target="_blank" '
        'rel="noopener noreferrer">Ссылка</a><br>'
    )
    assert plain_text == "Раздел Ячейка Ссылка"


def test_sanitizer_drops_malformed_urls_without_failing_request() -> None:
    sanitized, plain_text = sanitize_knowledge_html(
        '<p><a href="https://[">Повреждённая ссылка</a></p>'
    )

    assert sanitized == "<p><a>Повреждённая ссылка</a></p>"
    assert plain_text == "Повреждённая ссылка"


def test_personal_favorites_do_not_change_shared_version(knowledge_api) -> None:
    client, factory = knowledge_api
    first = add_user(client, factory, "first.curator")
    second = add_user(client, factory, "second.curator")
    first_headers = authenticate(client, first.login)
    document = create_document(client, first_headers)

    assert client.post(f"/api/v1/knowledge/documents/{document['id']}/favorite").status_code == 403
    favorite = client.post(
        f"/api/v1/knowledge/documents/{document['id']}/favorite", headers=first_headers
    )
    repeat = client.post(
        f"/api/v1/knowledge/documents/{document['id']}/favorite", headers=first_headers
    )
    first_list = client.get("/api/v1/knowledge/documents?favorite=true", headers=first_headers)

    second_headers = authenticate(client, second.login)
    second_list = client.get("/api/v1/knowledge/documents", headers=second_headers)
    second_favorites = client.get(
        "/api/v1/knowledge/documents?favorite=true", headers=second_headers
    )

    assert favorite.status_code == repeat.status_code == 204
    assert first_list.json()["items"][0]["is_favorite"] is True
    assert second_list.json()["items"][0]["is_favorite"] is False
    assert second_list.json()["items"][0]["version"] == 1
    assert second_favorites.json()["items"] == []

    removed = client.post(
        f"/api/v1/knowledge/documents/{document['id']}/unfavorite", headers=second_headers
    )
    assert removed.status_code == 204

    first_headers = authenticate(client, first.login)
    archived = client.post(
        f"/api/v1/knowledge/documents/{document['id']}/archive",
        json={"expected_version": 1},
        headers=first_headers,
    )
    archived_list = client.get(
        "/api/v1/knowledge/documents?favorite=true&include_archived=true",
        headers=first_headers,
    )
    restored = client.post(
        f"/api/v1/knowledge/documents/{document['id']}/restore",
        json={"expected_version": 2},
        headers=first_headers,
    )
    assert archived.status_code == restored.status_code == 200
    assert archived_list.json()["items"][0]["is_favorite"] is True
    assert restored.json()["is_favorite"] is True


def test_pagination_filters_search_and_rejects_tampered_cursor(knowledge_api) -> None:
    client, factory = knowledge_api
    admin = add_user(client, factory, "search.admin")
    headers = authenticate(client, admin.login)
    first = create_document(client, headers, "Альфа резюме")
    second = create_document(client, headers, "Бета портфолио")
    chapter_payload = {
        "kind": "chapter",
        "title": "Глава про собеседование",
        "html": "<p>Системный дизайн и архитектура</p>",
        "position": 1,
    }
    chapter = client.post(
        "/api/v1/knowledge/documents", json=chapter_payload, headers=headers
    ).json()

    page = client.get("/api/v1/knowledge/documents?limit=2", headers=headers)
    next_page = client.get(
        f"/api/v1/knowledge/documents?limit=2&cursor={page.json()['next_cursor']}",
        headers=headers,
    )
    prompts = client.get("/api/v1/knowledge/documents?kind=prompt", headers=headers)
    category = client.get(
        "/api/v1/knowledge/documents?category=%D0%94%D1%80%D1%83%D0%B3%D0%B8%D0%B5",
        headers=headers,
    )
    search = client.get(
        "/api/v1/knowledge/documents?q=%D0%B0%D1%80%D1%85%D0%B8%D1%82%D0%B5%D0%BA%D1%82%D1%83%D1%80%D0%B0",
        headers=headers,
    )
    wildcard = client.get("/api/v1/knowledge/documents?q=%25", headers=headers)
    invalid = client.get("/api/v1/knowledge/documents?cursor=not-a-cursor", headers=headers)
    unknown = client.get("/api/v1/knowledge/documents?cursor=bWlzc2luZw", headers=headers)

    assert page.status_code == next_page.status_code == 200
    assert len(page.json()["items"]) == 2
    assert page.json()["next_cursor"]
    assert len(next_page.json()["items"]) == 1
    assert {item["id"] for item in prompts.json()["items"]} == {first["id"], second["id"]}
    assert {item["id"] for item in category.json()["items"]} == {first["id"], second["id"]}
    assert [item["id"] for item in search.json()["items"]] == [chapter["id"]]
    assert wildcard.json()["items"] == []
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_cursor"
    assert unknown.status_code == 422


def test_stale_update_and_lifecycle_conflicts_return_409(knowledge_api) -> None:
    client, factory = knowledge_api
    admin = add_user(client, factory, "conflict.admin")
    headers = authenticate(client, admin.login)
    document = create_document(client, headers)

    first = client.patch(
        f"/api/v1/knowledge/documents/{document['id']}",
        json={"expected_version": 1, "title": "Первая версия"},
        headers=headers,
    )
    stale = client.patch(
        f"/api/v1/knowledge/documents/{document['id']}",
        json={"expected_version": 1, "title": "Потерянная версия"},
        headers=headers,
    )
    stale_archive = client.post(
        f"/api/v1/knowledge/documents/{document['id']}/archive",
        json={"expected_version": 1},
        headers=headers,
    )

    assert first.status_code == 200
    assert stale.status_code == stale_archive.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"
    current = client.get(f"/api/v1/knowledge/documents/{document['id']}", headers=headers)
    assert current.json()["title"] == "Первая версия"


def test_concurrent_curator_edits_allow_exactly_one_writer(knowledge_api) -> None:
    client, factory = knowledge_api
    first = add_user(client, factory, "concurrent.first")
    second = add_user(client, factory, "concurrent.second")
    first_headers = authenticate(client, first.login)
    document = create_document(client, first_headers)
    second_client = TestClient(client.app)
    second_headers = authenticate(second_client, second.login)
    barrier = Barrier(2)

    def patch(test_client: TestClient, headers: dict[str, str], title: str) -> int:
        barrier.wait()
        return test_client.patch(
            f"/api/v1/knowledge/documents/{document['id']}",
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
        persisted = database.get(KnowledgeDocument, document["id"])
        assert persisted.version == 2
        assert persisted.title in {"Первая запись", "Вторая запись"}


def test_audit_failure_rolls_back_document_update(knowledge_api, monkeypatch) -> None:
    client, factory = knowledge_api
    admin = add_user(client, factory, "atomic.admin")
    headers = authenticate(client, admin.login)
    document = create_document(client, headers)

    def fail_audit(*args, **kwargs) -> None:
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr(knowledge_service, "record_audit", fail_audit)
    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        client.patch(
            f"/api/v1/knowledge/documents/{document['id']}",
            json={"expected_version": 1, "title": "Не должно сохраниться"},
            headers=headers,
        )

    with factory() as database:
        persisted = database.get(KnowledgeDocument, document["id"])
        assert persisted.title == "Синтетический промпт"
        assert persisted.version == 1


def test_students_inactive_admins_csrf_and_cross_site_requests_are_denied(knowledge_api) -> None:
    client, factory = knowledge_api
    admin = add_user(client, factory, "rbac.admin")
    student = add_user(client, factory, "rbac.student", role=UserRole.STUDENT)
    temporary = add_user(client, factory, "temporary.admin", must_change_password=True)
    admin_headers = authenticate(client, admin.login)
    document = create_document(client, admin_headers)

    student_headers = authenticate(client, student.login)
    assert client.get("/api/v1/knowledge/documents", headers=student_headers).status_code == 403
    assert (
        client.get(
            f"/api/v1/knowledge/documents/{document['id']}", headers=student_headers
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/knowledge/documents/{document['id']}",
            json={"expected_version": 1, "title": "Нельзя"},
            headers=student_headers,
        ).status_code
        == 403
    )

    admin_headers = authenticate(client, admin.login)
    assert client.post("/api/v1/knowledge/documents", json=document_payload()).status_code == 403
    cross_site = client.post(
        "/api/v1/knowledge/documents",
        json=document_payload(),
        headers={**admin_headers, "Origin": "https://attacker.example"},
    )
    assert cross_site.status_code == 403

    temporary_headers = authenticate(client, temporary.login)
    temporary_access = client.get("/api/v1/knowledge/documents", headers=temporary_headers)
    assert temporary_access.status_code == 403
    assert temporary_access.json()["error"]["code"] == "password_change_required"

    admin_headers = authenticate(client, admin.login)
    with factory.begin() as database:
        database.get(User, admin.id).is_active = False
    assert client.get("/api/v1/knowledge/documents", headers=admin_headers).status_code == 401


def test_rejects_mass_assignment_invalid_payload_and_oversized_request(knowledge_api) -> None:
    client, factory = knowledge_api
    admin = add_user(client, factory, "validation.admin")
    headers = authenticate(client, admin.login)

    overposted = client.post(
        "/api/v1/knowledge/documents",
        json={**document_payload(), "version": 99, "created_by_user_id": admin.id},
        headers=headers,
    )
    empty = client.post(
        "/api/v1/knowledge/documents",
        json={**document_payload(), "html": "<script>only unsafe</script>"},
        headers=headers,
    )
    oversized = client.post(
        "/api/v1/knowledge/documents",
        content=b"{}",
        headers={**headers, "Content-Type": "application/json", "Content-Length": "1048577"},
    )
    oversized_stream = client.post(
        "/api/v1/knowledge/documents",
        content=iter((b"{" + b"x" * 600_000, b"x" * 600_000 + b"}")),
        headers={**headers, "Content-Type": "application/json"},
    )

    assert overposted.status_code == 422
    assert empty.status_code == 422
    assert "only unsafe" not in empty.text
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "payload_too_large"
    assert oversized_stream.status_code == 413
    assert oversized_stream.json()["error"]["code"] == "payload_too_large"


def test_physical_delete_is_not_exposed_and_missing_documents_are_safe(knowledge_api) -> None:
    client, factory = knowledge_api
    admin = add_user(client, factory, "lifecycle.admin")
    headers = authenticate(client, admin.login)
    document = create_document(client, headers)

    deleted = client.delete(f"/api/v1/knowledge/documents/{document['id']}", headers=headers)
    missing = client.get(
        "/api/v1/knowledge/documents/00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    existing = client.get(f"/api/v1/knowledge/documents/{document['id']}", headers=headers)

    assert deleted.status_code == 405
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert existing.status_code == 200
