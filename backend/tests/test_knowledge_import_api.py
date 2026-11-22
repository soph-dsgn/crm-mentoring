from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.knowledge import import_service
from app.modules.knowledge.models import (
    KnowledgeDocument,
    KnowledgeFavorite,
    KnowledgeImportMapping,
    KnowledgeImportRun,
    KnowledgeLibraryState,
    KnowledgeLibraryStatus,
)
from app.modules.users.audit import AuditAction, AuditEvent
from app.modules.users.models import User, UserRole
from tests.test_knowledge_api import add_user, authenticate

pytest_plugins = ["tests.test_knowledge_api"]


def knowledge_data() -> dict[str, object]:
    return {
        "version": 1,
        "prompts": [
            {
                "id": "synthetic-prompt-1",
                "title": "Синтетический промпт",
                "category": "Другие",
                "html": (
                    '<p>Только тестовые данные<script>alert("xss")</script>'
                    '<a href="javascript:alert(1)">ссылка</a></p>'
                ),
                "text": "Только тестовые данные",
                "sourceId": "synthetic:prompt",
                "sourceRevision": "1",
                "sourceHash": "synthetic",
                "edited": False,
                "deleted": False,
                "favorite": True,
                "updatedAt": "2026-01-01T00:00:00Z",
                "order": 0,
            }
        ],
        "chapters": [],
        "importedAt": "2026-01-01T00:00:00Z",
    }


def make_owner(knowledge_api):
    client, factory = knowledge_api
    owner = add_user(client, factory, "knowledge.import.owner")
    with factory.begin() as database:
        database.get(User, owner.id).is_owner = True
        state = database.get(KnowledgeLibraryState, 1)
        state.status = KnowledgeLibraryStatus.PENDING
        state.activated_at = None
        state.activated_by_user_id = None
    return client, factory, owner, authenticate(client, owner.login)


def test_validate_knowledge_data_is_read_only(knowledge_api) -> None:
    client, factory, _, headers = make_owner(knowledge_api)

    response = client.post(
        "/api/v1/knowledge/imports/validate",
        json={"source": knowledge_data(), "source_format": "knowledge_data_v1", "mode": "initial"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert response.json()["counts"]["new_documents"] == 1
    assert response.json()["checksum"]
    with factory() as database:
        assert database.scalar(select(func.count(KnowledgeDocument.id))) == 0
        assert database.scalar(select(func.count(KnowledgeImportRun.id))) == 0
        assert database.scalar(select(func.count(KnowledgeImportMapping.id))) == 0
        state = database.get(KnowledgeLibraryState, 1)
        assert state.status is KnowledgeLibraryStatus.PENDING
        assert state.version == 1


def test_pending_library_blocks_regular_document_api(knowledge_api) -> None:
    client, _, _, headers = make_owner(knowledge_api)

    response = client.get("/api/v1/knowledge/documents", headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "knowledge_library_pending"


def validate(client, headers, body: dict[str, object]) -> dict[str, object]:
    response = client.post("/api/v1/knowledge/imports/validate", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def confirmed(body: dict[str, object], preview: dict[str, object]) -> dict[str, object]:
    return {**body, "confirmation_checksum": preview["checksum"], "confirm": True}


def test_confirmed_initial_import_activates_once_and_sanitizes_content(knowledge_api) -> None:
    client, factory, owner, headers = make_owner(knowledge_api)
    body = {"source": knowledge_data(), "source_format": "knowledge_data_v1", "mode": "initial"}
    preview = validate(client, headers, body)

    imported = client.post(
        "/api/v1/knowledge/imports", json=confirmed(body, preview), headers=headers
    )
    replay = client.post(
        "/api/v1/knowledge/imports", json=confirmed(body, preview), headers=headers
    )
    state_response = client.get("/api/v1/knowledge/library-state", headers=headers)

    assert imported.status_code == 201, imported.text
    assert imported.json()["library_status"] == "active"
    assert imported.json()["idempotent_replay"] is False
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["import_run_id"] == imported.json()["import_run_id"]
    assert state_response.json()["status"] == "active"
    with factory() as database:
        document = database.scalar(select(KnowledgeDocument))
        assert document.plain_text == "Только тестовые данные ссылка"
        assert "script" not in document.html
        assert "javascript:" not in document.html
        assert database.get(KnowledgeFavorite, (owner.id, document.id)) is not None
        assert database.scalar(select(func.count(KnowledgeImportRun.id))) == 1
        assert database.scalar(select(func.count(KnowledgeImportMapping.id))) == 1
        state = database.get(KnowledgeLibraryState, 1)
        assert state.status is KnowledgeLibraryStatus.ACTIVE
        assert state.activated_by_user_id == owner.id
        events = list(
            database.scalars(
                select(AuditEvent).where(
                    AuditEvent.action.in_(
                        [
                            AuditAction.KNOWLEDGE_IMPORTED,
                            AuditAction.KNOWLEDGE_LIBRARY_ACTIVATED,
                        ]
                    )
                )
            )
        )
        assert len(events) == 2
        assert all("html" not in event.details for event in events)
        assert "Только тестовые данные" not in repr([event.details for event in events])


def test_checksum_source_change_and_failed_import_never_activate(knowledge_api) -> None:
    client, factory, _, headers = make_owner(knowledge_api)
    body = {"source": knowledge_data(), "source_format": "knowledge_data_v1", "mode": "initial"}
    preview = validate(client, headers, body)
    changed = knowledge_data()
    changed["prompts"][0]["title"] = "Изменённый источник"

    response = client.post(
        "/api/v1/knowledge/imports",
        json={
            "source": changed,
            "source_format": "knowledge_data_v1",
            "mode": "initial",
            "confirmation_checksum": preview["checksum"],
            "confirm": True,
        },
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "validation_changed"
    with factory() as database:
        assert database.scalar(select(func.count(KnowledgeDocument.id))) == 0
        assert database.scalar(select(func.count(KnowledgeImportRun.id))) == 0
        assert database.get(KnowledgeLibraryState, 1).status is KnowledgeLibraryStatus.PENDING


def test_confirmation_expires_when_server_preview_changes(knowledge_api) -> None:
    client, factory, owner, headers = make_owner(knowledge_api)
    body = {"source": knowledge_data(), "source_format": "knowledge_data_v1", "mode": "initial"}
    preview = validate(client, headers, body)
    with factory.begin() as database:
        database.add(
            KnowledgeDocument(
                kind="prompt",
                title="Синтетический промпт",
                category="Другие",
                html="<p>Параллельное изменение</p>",
                plain_text="Параллельное изменение",
                search_text="синтетический промпт параллельное изменение",
                position=0,
                created_by_user_id=owner.id,
                updated_by_user_id=owner.id,
            )
        )

    response = client.post(
        "/api/v1/knowledge/imports", json=confirmed(body, preview), headers=headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "validation_changed"
    with factory() as database:
        assert database.scalar(select(func.count(KnowledgeImportRun.id))) == 0
        assert database.get(KnowledgeLibraryState, 1).status is KnowledgeLibraryStatus.PENDING


def test_additional_parsed_documents_support_formats_and_owner_export(knowledge_api) -> None:
    client, factory, owner, owner_headers = make_owner(knowledge_api)
    initial_body = {
        "source": knowledge_data(),
        "source_format": "knowledge_data_v1",
        "mode": "initial",
    }
    initial_preview = validate(client, owner_headers, initial_body)
    assert (
        client.post(
            "/api/v1/knowledge/imports",
            json=confirmed(initial_body, initial_preview),
            headers=owner_headers,
        ).status_code
        == 201
    )
    curator = add_user(client, factory, "knowledge.additional.curator")
    curator_headers = authenticate(client, curator.login)
    documents = []
    for index, source_format in enumerate(("docx", "html", "markdown"), start=1):
        documents.append(
            {
                "id": f"parsed-{index}",
                "kind": "chapter" if index == 1 else "prompt",
                "format": source_format,
                "title": f"Разобранный материал {index}",
                "category": "Другие",
                "html": f"<h2>Материал {index}</h2><p>Синтетика</p>",
                "text": "ignored client text",
                "sourceId": f"file:synthetic-{source_format}",
                "sourceRevision": "",
                "sourceHash": "client-hash-is-not-trusted",
                "edited": False,
                "deleted": index == 3,
                "favorite": index == 2,
                "updatedAt": "2026-01-02T00:00:00Z",
                "order": index,
            }
        )
    body = {
        "source": {"version": 1, "documents": documents, "importedAt": "2026-01-02T00:00:00Z"},
        "source_format": "parsed_documents",
        "mode": "additional",
    }
    preview = validate(client, curator_headers, body)
    imported = client.post(
        "/api/v1/knowledge/imports", json=confirmed(body, preview), headers=curator_headers
    )
    second_curator = add_user(client, factory, "knowledge.additional.second")
    second_headers = authenticate(client, second_curator.login)
    second_preview = validate(client, second_headers, body)
    second_import = client.post(
        "/api/v1/knowledge/imports",
        json=confirmed(body, second_preview),
        headers=second_headers,
    )
    curator_export = client.get("/api/v1/knowledge/export", headers=curator_headers)
    owner_headers = authenticate(client, owner.login)
    owner_export = client.get("/api/v1/knowledge/export", headers=owner_headers)

    assert preview["counts"]["new_documents"] == 2
    assert preview["counts"]["archived_records"] == 1
    assert imported.status_code == 201
    assert second_preview["checksum"] != preview["checksum"]
    assert second_preview["counts"]["exact_duplicates"] == 3
    assert second_import.status_code == 201
    assert curator_export.status_code == 403
    assert owner_export.status_code == 200
    assert owner_export.headers["cache-control"] == "no-store"
    assert (
        owner_export.headers["content-disposition"]
        == 'attachment; filename="knowledge-backup.json"'
    )
    assert owner_export.json()["schema_version"] == 1
    assert len(owner_export.json()["documents"]) == 4
    assert len(owner_export.json()["favorites"]) == 3
    assert len(owner_export.json()["import_runs"]) == 3
    assert len(owner_export.json()["mappings"]) == 7
    with factory() as database:
        archived = database.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.title == "Разобранный материал 3")
        )
        assert archived.archived_at is not None


def test_duplicates_conflicts_and_explicit_versioned_overwrite(knowledge_api) -> None:
    client, factory, _, headers = make_owner(knowledge_api)
    initial = {"source": knowledge_data(), "source_format": "knowledge_data_v1", "mode": "initial"}
    initial_preview = validate(client, headers, initial)
    client.post(
        "/api/v1/knowledge/imports", json=confirmed(initial, initial_preview), headers=headers
    )
    duplicate = {**initial, "mode": "additional"}
    duplicate_preview = validate(client, headers, duplicate)
    assert duplicate_preview["valid"] is True
    assert duplicate_preview["counts"]["exact_duplicates"] == 1
    duplicate_result = client.post(
        "/api/v1/knowledge/imports",
        json=confirmed(duplicate, duplicate_preview),
        headers=headers,
    )
    assert duplicate_result.status_code == 201
    with factory() as database:
        assert database.scalar(select(func.count(KnowledgeDocument.id))) == 1

    changed_source = knowledge_data()
    changed_source["prompts"][0]["html"] = "<p>Новая безопасная версия</p>"
    changed = {"source": changed_source, "source_format": "knowledge_data_v1", "mode": "additional"}
    conflict = validate(client, headers, changed)
    assert conflict["valid"] is False
    assert conflict["counts"]["conflicts"] == 1
    source_key = conflict["items"][0]["source_key"]
    resolution_body = {
        **changed,
        "resolutions": {source_key: {"action": "overwrite", "expected_version": 1}},
    }
    resolved = validate(client, headers, resolution_body)
    assert resolved["valid"] is True
    assert resolved["counts"]["resolved_conflicts"] == 1
    overwrite = client.post(
        "/api/v1/knowledge/imports",
        json=confirmed(resolution_body, resolved),
        headers=headers,
    )
    assert overwrite.status_code == 201
    with factory() as database:
        document = database.scalar(select(KnowledgeDocument))
        assert document.plain_text == "Новая безопасная версия"
        assert document.version == 2


def test_exact_duplicates_inside_one_source_map_to_one_document(knowledge_api) -> None:
    client, factory, _, headers = make_owner(knowledge_api)
    source = knowledge_data()
    duplicate = {**source["prompts"][0], "id": "synthetic-prompt-copy"}
    source["prompts"].append(duplicate)
    body = {"source": source, "source_format": "knowledge_data_v1", "mode": "initial"}

    preview = validate(client, headers, body)
    imported = client.post(
        "/api/v1/knowledge/imports", json=confirmed(body, preview), headers=headers
    )

    assert preview["counts"]["new_documents"] == 1
    assert preview["counts"]["exact_duplicates"] == 1
    assert imported.status_code == 201
    assert len(imported.json()["mappings"]) == 2
    assert len(set(imported.json()["mappings"].values())) == 1
    with factory() as database:
        assert database.scalar(select(func.count(KnowledgeDocument.id))) == 1


def test_unsupported_fields_are_reported_without_writes(knowledge_api) -> None:
    client, factory, _, headers = make_owner(knowledge_api)
    source = knowledge_data()
    source["unexpectedRoot"] = "not accepted"
    source["prompts"][0]["rawSecret"] = "not echoed"
    body = {"source": source, "source_format": "knowledge_data_v1", "mode": "initial"}

    preview = validate(client, headers, body)

    assert preview["valid"] is False
    assert preview["counts"]["unsupported_records"] == 2
    assert {issue["code"] for issue in preview["issues"]} == {"unsupported_field"}
    assert "not echoed" not in str(preview)
    rejected = client.post(
        "/api/v1/knowledge/imports", json=confirmed(body, preview), headers=headers
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "import_conflict"
    with factory() as database:
        assert database.scalar(select(func.count(KnowledgeDocument.id))) == 0
        assert database.get(KnowledgeLibraryState, 1).status is KnowledgeLibraryStatus.PENDING


def test_initial_import_is_owner_only_and_mutations_require_csrf(knowledge_api) -> None:
    client, factory = knowledge_api
    curator = add_user(client, factory, "knowledge.initial.curator")
    student = add_user(client, factory, "knowledge.import.student", role=UserRole.STUDENT)
    with factory.begin() as database:
        database.get(KnowledgeLibraryState, 1).status = KnowledgeLibraryStatus.PENDING
    body = {"source": knowledge_data(), "source_format": "knowledge_data_v1", "mode": "initial"}

    curator_headers = authenticate(client, curator.login)
    assert (
        client.post(
            "/api/v1/knowledge/imports/validate", json=body, headers=curator_headers
        ).status_code
        == 403
    )
    student_headers = authenticate(client, student.login)
    assert (
        client.post(
            "/api/v1/knowledge/imports/validate", json=body, headers=student_headers
        ).status_code
        == 403
    )
    owner = add_user(client, factory, "knowledge.csrf.owner")
    with factory.begin() as database:
        database.get(User, owner.id).is_owner = True
    owner_headers = authenticate(client, owner.login)
    assert client.post("/api/v1/knowledge/imports/validate", json=body).status_code == 403
    cross_site = client.post(
        "/api/v1/knowledge/imports/validate",
        json=body,
        headers={**owner_headers, "Origin": "https://attacker.example"},
    )
    assert cross_site.status_code == 403


def test_audit_failure_rolls_back_import_and_activation(knowledge_api, monkeypatch) -> None:
    client, factory, _, headers = make_owner(knowledge_api)
    body = {"source": knowledge_data(), "source_format": "knowledge_data_v1", "mode": "initial"}
    preview = validate(client, headers, body)

    def fail_audit(*args, **kwargs) -> None:
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr(import_service, "record_audit", fail_audit)
    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        client.post("/api/v1/knowledge/imports", json=confirmed(body, preview), headers=headers)

    with factory() as database:
        assert database.scalar(select(func.count(KnowledgeDocument.id))) == 0
        assert database.scalar(select(func.count(KnowledgeImportRun.id))) == 0
        assert database.get(KnowledgeLibraryState, 1).status is KnowledgeLibraryStatus.PENDING


def test_non_idempotent_commit_conflict_never_returns_success(knowledge_api, monkeypatch) -> None:
    client, factory, _, headers = make_owner(knowledge_api)
    body = {"source": knowledge_data(), "source_format": "knowledge_data_v1", "mode": "initial"}
    preview = validate(client, headers, body)
    original_commit = Session.commit
    failed = False

    def fail_first_commit(database: Session) -> None:
        nonlocal failed
        if not failed:
            failed = True
            raise IntegrityError("synthetic conflict", {}, RuntimeError("synthetic conflict"))
        original_commit(database)

    monkeypatch.setattr(Session, "commit", fail_first_commit)
    response = client.post(
        "/api/v1/knowledge/imports", json=confirmed(body, preview), headers=headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "import_conflict"
    with factory() as database:
        assert database.scalar(select(func.count(KnowledgeDocument.id))) == 0
        assert database.scalar(select(func.count(KnowledgeImportRun.id))) == 0
        assert database.get(KnowledgeLibraryState, 1).status is KnowledgeLibraryStatus.PENDING


def test_import_size_limit_rejects_header_and_streamed_body(knowledge_api) -> None:
    client, _, _, headers = make_owner(knowledge_api)
    oversized_header = client.post(
        "/api/v1/knowledge/imports/validate",
        content=b"{}",
        headers={
            **headers,
            "Content-Type": "application/json",
            "Content-Length": str(5 * 1024 * 1024 + 1),
        },
    )
    oversized_stream = client.post(
        "/api/v1/knowledge/imports/validate",
        content=iter((b"{" + b"x" * 3_000_000, b"x" * 3_000_000 + b"}")),
        headers={**headers, "Content-Type": "application/json"},
    )

    assert oversized_header.status_code == oversized_stream.status_code == 413
    assert oversized_header.json()["error"]["code"] == "payload_too_large"


def test_concurrent_identical_initial_imports_create_one_run(knowledge_api) -> None:
    client, factory, owner, headers = make_owner(knowledge_api)
    body = {"source": knowledge_data(), "source_format": "knowledge_data_v1", "mode": "initial"}
    preview = validate(client, headers, body)
    payload = confirmed(body, preview)
    second_client = TestClient(client.app)
    second_headers = authenticate(second_client, owner.login)
    barrier = Barrier(2)

    def submit(test_client: TestClient, request_headers: dict[str, str]) -> int:
        barrier.wait()
        return test_client.post(
            "/api/v1/knowledge/imports", json=payload, headers=request_headers
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = [
                future.result()
                for future in (
                    executor.submit(submit, client, headers),
                    executor.submit(submit, second_client, second_headers),
                )
            ]
    finally:
        second_client.close()

    assert sorted(statuses) == [200, 201]
    with factory() as database:
        assert database.scalar(select(func.count(KnowledgeDocument.id))) == 1
        assert database.scalar(select(func.count(KnowledgeImportRun.id))) == 1
        assert database.get(KnowledgeLibraryState, 1).status is KnowledgeLibraryStatus.ACTIVE


def test_concurrent_different_initial_imports_allow_one_cutover(knowledge_api) -> None:
    client, factory, owner, headers = make_owner(knowledge_api)
    first_body = {
        "source": knowledge_data(),
        "source_format": "knowledge_data_v1",
        "mode": "initial",
    }
    second_source = knowledge_data()
    second_source["prompts"][0]["id"] = "synthetic-prompt-2"
    second_source["prompts"][0]["title"] = "Другой синтетический промпт"
    second_body = {
        "source": second_source,
        "source_format": "knowledge_data_v1",
        "mode": "initial",
    }
    first_payload = confirmed(first_body, validate(client, headers, first_body))
    second_payload = confirmed(second_body, validate(client, headers, second_body))
    second_client = TestClient(client.app)
    second_headers = authenticate(second_client, owner.login)
    barrier = Barrier(2)

    def submit(
        test_client: TestClient, payload: dict[str, object], request_headers: dict[str, str]
    ) -> int:
        barrier.wait()
        return test_client.post(
            "/api/v1/knowledge/imports", json=payload, headers=request_headers
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = [
                future.result()
                for future in (
                    executor.submit(submit, client, first_payload, headers),
                    executor.submit(submit, second_client, second_payload, second_headers),
                )
            ]
    finally:
        second_client.close()

    assert sorted(statuses) == [201, 409]
    with factory() as database:
        assert database.scalar(select(func.count(KnowledgeDocument.id))) == 1
        assert database.scalar(select(func.count(KnowledgeImportRun.id))) == 1
        assert database.get(KnowledgeLibraryState, 1).status is KnowledgeLibraryStatus.ACTIVE


def assert_concurrent_additional_imports_serialize_same_source(knowledge_api) -> None:
    client, factory, owner, headers = make_owner(knowledge_api)
    with factory.begin() as database:
        database.get(KnowledgeLibraryState, 1).status = KnowledgeLibraryStatus.ACTIVE
    first_body = {
        "source": knowledge_data(),
        "source_format": "knowledge_data_v1",
        "mode": "additional",
    }
    changed_source = knowledge_data()
    changed_source["prompts"][0]["html"] = "<p>Конкурирующая версия</p>"
    second_body = {
        "source": changed_source,
        "source_format": "knowledge_data_v1",
        "mode": "additional",
    }
    first_payload = confirmed(first_body, validate(client, headers, first_body))
    second_payload = confirmed(second_body, validate(client, headers, second_body))
    second_client = TestClient(client.app)
    second_headers = authenticate(second_client, owner.login)
    barrier = Barrier(2)

    def submit(
        test_client: TestClient, payload: dict[str, object], request_headers: dict[str, str]
    ) -> int:
        barrier.wait()
        return test_client.post(
            "/api/v1/knowledge/imports", json=payload, headers=request_headers
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = [
                future.result()
                for future in (
                    executor.submit(submit, client, first_payload, headers),
                    executor.submit(submit, second_client, second_payload, second_headers),
                )
            ]
    finally:
        second_client.close()

    assert sorted(statuses) == [201, 409]
    with factory() as database:
        assert database.scalar(select(func.count(KnowledgeDocument.id))) == 1
        assert database.scalar(select(func.count(KnowledgeImportRun.id))) == 1
        assert database.scalar(select(func.count(KnowledgeImportMapping.id))) == 1
