from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.api.errors import ApiError
from app.modules.strategies.models import (
    Strategy,
    StrategySection,
    StrategyTask,
    StudyStatus,
    TaskHistory,
)
from app.modules.strategies.notion_import import (
    MAX_PDF_BYTES,
    join_wrapped_lines,
    parse_notion_pdf,
)
from app.modules.students.models import Student
from app.modules.users.audit import AuditEvent
from tests.test_strategies_tasks_api import (
    add_group,
    add_student,
    add_user,
    authenticate,
)
from tests.test_strategies_tasks_api import (
    strategy_api as strategy_api,  # noqa: F401  (pytest fixture)
)

FIXTURE = Path(__file__).parent / "fixtures" / "notion-strategy-synthetic.pdf"


@pytest.fixture(scope="module")
def fixture_pdf() -> bytes:
    return FIXTURE.read_bytes()


@pytest.fixture(scope="module")
def draft(fixture_pdf: bytes):
    return parse_notion_pdf(fixture_pdf)


def test_parser_reads_sections_tasks_statuses_and_links(draft) -> None:
    assert draft.source_title == "Тестовая | Стратегия действий"
    assert [section.title for section in draft.sections] == ["Часть 1", "Часть 2"]
    first = draft.sections[0].tasks
    assert [task.title for task in first] == [
        "Зарегистрироваться в Notion",
        "Пройти диагностику",
        "Подготовить резюме",
        "Задача без статуса",
    ]
    assert [task.study_status for task in first] == [
        StudyStatus.DONE,
        StudyStatus.IN_PROGRESS,
        StudyStatus.HOLD,
        StudyStatus.NOT_STARTED,
    ]
    assert first[0].materials[0] == "https://example.com/guide"
    assert first[1].period_text == "1-2 недели"
    assert first[1].description == "Записать выводы\n1) Сравнить с целью"
    assert [warning.code for warning in draft.warnings] == ["status_missing"]


def test_parser_ignores_bold_text_inside_cells(draft) -> None:
    assert "Промпт для кейса" not in [section.title for section in draft.sections]
    assert draft.sections[0].tasks[2].description == "Промпт для кейса внутри ячейки"


def test_parser_keeps_rows_split_across_pages_and_headerless_continuations(draft) -> None:
    tasks = draft.sections[1].tasks
    assert [task.title for task in tasks][-2:] == [
        "Длинная задача через разрыв страницы",
        "Финальная задача",
    ]
    long_text = tasks[-2].description
    assert long_text.startswith("Шаг 1 синтетического плана")
    assert long_text.endswith("Шаг 70 синтетического плана")
    assert "\n" not in long_text
    assert all(f"Шаг {number} " in long_text for number in range(1, 71))
    assert tasks[-1].study_status == StudyStatus.DONE


def test_parser_maps_points_and_telegram(draft) -> None:
    assert draft.profile.point_a == (
        "Опыт работы: Синтетический опыт в графическом дизайне\nЦель: Стать продуктовым дизайнером"
    )
    assert draft.profile.point_b == "Резюме: Готово к отправке"
    assert str(draft.profile.telegram) == "https://t.me/test_handle"


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (
            [("Зарегистрироватьс", 0.2, 5.0), ("я в Notion", 40.0, 5.0)],
            "Зарегистрироваться в Notion",
        ),
        (
            [("https://example.com/very/lo", 0.1, 5.0), ("ng/path", 30.0, 5.0)],
            "https://example.com/very/long/path",
        ),
        ([("Посмотрет", 0.5, 5.0), ("ь видео", 30.0, 5.0)], "Посмотреть видео"),
        ([("разобраться", 0.5, 5.0), ("в теме", 30.0, 5.0)], "разобраться в теме"),
        ([("полностью", 0.5, 5.0), ("модуль", 30.0, 5.0)], "полностью модуль"),
        ([("интерактивная", 9.0, 5.0), ("стратегия", 30.0, 5.0)], "интерактивная стратегия"),
        ([("Шаги:", 30.0, 5.0), ("1) Первый", 30.0, 5.0)], "Шаги:\n1) Первый"),
        ([("ссылка", 0.1, 5.0), ("https://example.com", 30.0, 5.0)], "ссылка https://example.com"),
    ],
)
def test_join_wrapped_lines(lines, expected) -> None:
    assert join_wrapped_lines(lines) == expected


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"not a pdf", "unsupported_file"),
        (b"%PDF-1.7\n%%EOF", "unreadable_pdf"),
    ],
)
def test_parser_rejects_invalid_documents(data: bytes, code: str) -> None:
    with pytest.raises(ApiError) as error:
        parse_notion_pdf(data)
    assert error.value.status_code == 422
    assert error.value.code == code


def _apply_payload(draft, *, version: int = 1, profile: dict | None = None) -> dict:
    return {
        "expected_version": version,
        "source": {
            "file_name": "strategy.pdf",
            "title": draft.source_title,
            "sha256": draft.sha256,
        },
        "profile": profile if profile is not None else draft.profile.model_dump(mode="json"),
        "sections": [section.model_dump(mode="json") for section in draft.sections],
    }


def _setup(strategy_api):
    client, factory = strategy_api
    owner = add_user(client, factory, "owner", owner=True)
    curator = add_user(client, factory, "curator")
    foreign = add_user(client, factory, "foreign")
    group = add_group(factory, curator)
    student = add_student(factory, group, "Синтетическая ученица")
    return client, factory, owner, curator, foreign, student


def test_preview_requires_write_access_csrf_and_pdf(strategy_api, fixture_pdf) -> None:
    client, _, _, curator, foreign, student = _setup(strategy_api)
    url = f"/api/v1/students/{student.id}/strategy-import/preview"
    pdf_headers = {"Content-Type": "application/pdf"}

    assert client.post(url, content=fixture_pdf, headers=pdf_headers).status_code == 401

    foreign_headers = authenticate(client, foreign.login)
    foreign_response = client.post(
        url, content=fixture_pdf, headers={**foreign_headers, **pdf_headers}
    )
    assert foreign_response.status_code == 403

    headers = authenticate(client, curator.login)
    no_csrf = client.post(
        url, content=fixture_pdf, headers={"Origin": "http://testserver", **pdf_headers}
    )
    assert no_csrf.status_code == 403
    wrong_type = client.post(
        url, content=fixture_pdf, headers={**headers, "Content-Type": "application/json"}
    )
    assert wrong_type.status_code == 415
    too_large = client.post(
        url,
        content=b"%PDF" + b"0" * MAX_PDF_BYTES,
        headers={**headers, **pdf_headers},
    )
    assert too_large.status_code == 413
    not_pdf = client.post(url, content=b"hello", headers={**headers, **pdf_headers})
    assert not_pdf.status_code == 422
    assert not_pdf.json()["error"]["code"] == "unsupported_file"

    response = client.post(url, content=fixture_pdf, headers={**headers, **pdf_headers})
    assert response.status_code == 200
    body = response.json()
    assert [section["title"] for section in body["sections"]] == ["Часть 1", "Часть 2"]
    assert body["profile"]["telegram"] == "https://t.me/test_handle"


def test_preview_does_not_write(strategy_api, fixture_pdf) -> None:
    client, factory, _, curator, _, student = _setup(strategy_api)
    headers = authenticate(client, curator.login)
    response = client.post(
        f"/api/v1/students/{student.id}/strategy-import/preview",
        content=fixture_pdf,
        headers={**headers, "Content-Type": "application/pdf"},
    )
    assert response.status_code == 200
    with factory() as database:
        assert database.scalar(select(Strategy)) is None
        assert database.get(Student, student.id).version == 1


def test_apply_creates_strategy_tasks_and_profile_in_one_step(strategy_api, draft) -> None:
    client, factory, _, curator, _, student = _setup(strategy_api)
    headers = authenticate(client, curator.login)

    response = client.post(
        f"/api/v1/students/{student.id}/strategy-import",
        json=_apply_payload(draft),
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    total = sum(len(section.tasks) for section in draft.sections)
    assert body["section_count"] == 2
    assert body["task_count"] == total
    assert body["student_version"] == 2
    with factory() as database:
        strategy = database.scalar(select(Strategy))
        assert strategy.source_metadata["notion_import"]["sha256"] == draft.sha256
        sections = database.scalars(
            select(StrategySection).order_by(StrategySection.position)
        ).all()
        assert [section.title for section in sections] == ["Часть 1", "Часть 2"]
        tasks = database.scalars(
            select(StrategyTask)
            .where(StrategyTask.section_id == sections[0].id)
            .order_by(StrategyTask.position)
        ).all()
        assert [task.study_status for task in tasks] == [
            StudyStatus.DONE,
            StudyStatus.IN_PROGRESS,
            StudyStatus.HOLD,
            StudyStatus.NOT_STARTED,
        ]
        assert tasks[0].links == {"primary": "https://example.com/guide"}
        assert len(database.scalars(select(TaskHistory)).all()) == total
        updated = database.get(Student, student.id)
        assert updated.point_a.startswith("Опыт работы:")
        assert updated.point_b == "Резюме: Готово к отправке"
        assert updated.links == {"telegram": "https://t.me/test_handle"}
        audit = database.scalar(select(AuditEvent).where(AuditEvent.action == "strategy_imported"))
        assert audit is not None
        assert audit.details["tasks"] == total


def test_apply_skips_unselected_profile_fields_and_reuses_empty_strategy(
    strategy_api, draft
) -> None:
    client, factory, _, curator, _, student = _setup(strategy_api)
    headers = authenticate(client, curator.login)
    created = client.post(f"/api/v1/students/{student.id}/strategy", json={}, headers=headers)
    assert created.status_code == 201

    response = client.post(
        f"/api/v1/students/{student.id}/strategy-import",
        json=_apply_payload(draft, profile={}),
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["strategy"]["id"] == created.json()["id"]
    with factory() as database:
        unchanged = database.get(Student, student.id)
        assert unchanged.version == 1
        assert unchanged.point_a == ""


def test_apply_rejects_non_empty_strategy_and_stale_profile(strategy_api, draft) -> None:
    client, factory, owner, _, _, student = _setup(strategy_api)
    headers = authenticate(client, owner.login)
    url = f"/api/v1/students/{student.id}/strategy-import"

    stale = client.post(url, json=_apply_payload(draft, version=7), headers=headers)
    assert stale.status_code == 409
    with factory() as database:
        assert database.scalar(select(StrategySection)) is None
        assert database.scalar(select(Strategy)) is None

    stale_without_profile = client.post(
        url, json=_apply_payload(draft, version=7, profile={}), headers=headers
    )
    assert stale_without_profile.status_code == 409

    assert client.post(url, json=_apply_payload(draft), headers=headers).status_code == 201
    repeated = client.post(url, json=_apply_payload(draft, version=2), headers=headers)
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "strategy_not_empty"
    with factory() as database:
        assert len(database.scalars(select(StrategySection)).all()) == 2


def test_apply_validates_payload_and_rbac(strategy_api, draft) -> None:
    client, _, _, _, foreign, student = _setup(strategy_api)
    url = f"/api/v1/students/{student.id}/strategy-import"
    headers = authenticate(client, foreign.login)
    assert client.post(url, json=_apply_payload(draft), headers=headers).status_code == 403

    invalid = _apply_payload(draft)
    invalid["sections"] = []
    assert client.post(url, json=invalid, headers=headers).status_code == 422
    invalid = _apply_payload(draft)
    invalid["source"]["sha256"] = "x"
    assert client.post(url, json=invalid, headers=headers).status_code == 422
    invalid = _apply_payload(draft)
    invalid["sections"][0]["tasks"][0]["study_status"] = "unknown"
    assert client.post(url, json=invalid, headers=headers).status_code == 422
