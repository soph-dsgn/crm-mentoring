from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlparse

from fastapi import status
from sqlalchemy import Date, DateTime, func, select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.modules.groups.models import Group, GroupStatus
from app.modules.homeworks.models import Homework, HomeworkHistory, HomeworkItem, HomeworkStatus
from app.modules.legacy_io.models import ImportRun, LegacyIdMapping
from app.modules.legacy_io.schemas import (
    ImportIssue,
    ImportResult,
    LegacyImportRequest,
    ValidationReport,
)
from app.modules.meetings.models import Meeting
from app.modules.strategies.models import (
    AnyaApproval,
    ApprovalStatus,
    ReviewStatus,
    Strategy,
    StrategySection,
    StrategyTask,
    StudyStatus,
    TaskHistory,
)
from app.modules.students.models import Student, StudentStage
from app.modules.users.audit import AuditAction, AuditEvent
from app.modules.users.models import User, UserRole
from app.modules.users.service import ensure_owner, record_audit

MAX_ITEMS = 10_000
ENTITY_KEYS = ("groups", "students", "sections", "tasks", "meetings", "homeworks")
ALLOWED_KEYS = {
    "groups": {
        "id",
        "name",
        "startsAt",
        "endsAt",
        "actualEndsAt",
        "status",
        "statusBeforeArchive",
        "notes",
        "createdAt",
        "durationMonths",
        "archived",
    },
    "students": {
        "id",
        "groupId",
        "name",
        "age",
        "photo",
        "avatarIndex",
        "stage",
        "stageKnown",
        "startsAt",
        "level",
        "desiredPosition",
        "careerGoal",
        "links",
        "background",
        "experience",
        "strengths",
        "growthAreas",
        "difficulties",
        "expectations",
        "personalNotes",
        "pointA",
        "pointB",
        "notes",
        "strategyUpdatedAt",
        "createdAt",
    },
    "sections": {"id", "studentId", "title", "order", "createdAt"},
    "tasks": {
        "id",
        "studentId",
        "title",
        "description",
        "stage",
        "status",
        "owner",
        "dueAt",
        "url",
        "comments",
        "order",
        "blocker",
        "createdAt",
        "updatedAt",
        "reviewStatus",
        "approvalStatus",
        "approvalType",
        "approvalSentAt",
        "approvalComment",
        "history",
        "sectionId",
        "studyStatus",
        "period",
        "sourceFile",
        "materials",
        "archivedAt",
    },
    "meetings": {"id", "studentId", "date", "title", "summary", "createdAt"},
    "homeworks": {
        "id",
        "studentId",
        "title",
        "text",
        "items",
        "status",
        "issuedAt",
        "submittedAt",
        "reviewedAt",
        "workUrl",
        "comment",
        "dueAt",
        "createdAt",
        "deletedAt",
    },
}
ALLOWED_ITEM_KEYS = {"taskId", "title", "description", "url", "materials", "dueAt"}


def canonical_checksum(source: dict[str, Any]) -> str:
    encoded = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _issue(code: str, entity: str, legacy_id: object = None) -> ImportIssue:
    return ImportIssue(code=code, entity=entity, legacy_id=str(legacy_id) if legacy_id else None)


def _valid_url(value: object) -> bool:
    if value in (None, ""):
        return True
    if not isinstance(value, str):
        return False
    return urlparse(value).scheme.lower() in {"http", "https"}


def _date(value: object, *, required: bool = False) -> date | None:
    if value in (None, ""):
        if required:
            raise ValueError
        return None
    return date.fromisoformat(str(value))


def _datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    raw = str(value)
    if len(raw) == 10:
        return datetime.combine(date.fromisoformat(raw), datetime.min.time())
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo else parsed


def _records(source: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = source.get(key, [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _validate_positions(
    conflicts: list[ImportIssue],
    records: list[dict[str, Any]],
    parent_keys: tuple[str, ...],
    entity: str,
) -> None:
    seen: set[tuple[object, ...]] = set()
    for record in records:
        position = record.get("order", 0)
        parent = tuple(record.get(key) for key in parent_keys)
        if not isinstance(position, int) or isinstance(position, bool) or position < 0:
            conflicts.append(_issue("invalid_order", entity, record.get("id")))
            continue
        key = (*parent, position)
        if key in seen:
            conflicts.append(_issue("duplicate_order", entity, record.get("id")))
        seen.add(key)


def validate_legacy(
    database: Session, actor: User, payload: LegacyImportRequest
) -> ValidationReport:
    ensure_owner(actor)
    source = payload.source
    checksum = canonical_checksum(source)
    conflicts: list[ImportIssue] = []
    warnings: list[str] = []
    version = source.get("version")
    if version not in {1, 2, 3}:
        conflicts.append(_issue("unsupported_version", "source", version))
        version = None
    root_allowed = {*ENTITY_KEYS, "version", "demo", "demoRevision", "importConflicts"}
    if set(source) - root_allowed:
        conflicts.append(_issue("unsupported_field", "source"))

    ids: dict[str, set[str]] = {}
    for entity in ENTITY_KEYS:
        raw = source.get(entity, [] if entity not in {"groups", "students", "tasks"} else None)
        if not isinstance(raw, list) or len(raw) > MAX_ITEMS:
            conflicts.append(_issue("invalid_collection", entity))
            ids[entity] = set()
            continue
        entity_ids: set[str] = set()
        for record in raw:
            if not isinstance(record, dict):
                conflicts.append(_issue("invalid_record", entity))
                continue
            legacy_id = record.get("id")
            if not isinstance(legacy_id, str) or not legacy_id or len(legacy_id) > 255:
                conflicts.append(_issue("invalid_id", entity, legacy_id))
                continue
            if legacy_id in entity_ids:
                conflicts.append(_issue("duplicate_id", entity, legacy_id))
            entity_ids.add(legacy_id)
            if set(record) - ALLOWED_KEYS[entity]:
                conflicts.append(_issue("unsupported_field", entity, legacy_id))
            if entity == "homeworks":
                items = record.get("items")
                if not isinstance(items, list) or len(items) > 500:
                    conflicts.append(_issue("invalid_collection", "homework_items", legacy_id))
                else:
                    if any(
                        not isinstance(item, dict) or set(item) - ALLOWED_ITEM_KEYS
                        for item in items
                    ):
                        conflicts.append(_issue("unsupported_field", "homework_items", legacy_id))
        ids[entity] = entity_ids

    for student in _records(source, "students"):
        if student.get("groupId") not in ids.get("groups", set()):
            conflicts.append(_issue("orphan_reference", "students", student.get("id")))
    section_by_id = {row.get("id"): row for row in _records(source, "sections")}
    _validate_positions(conflicts, list(section_by_id.values()), ("studentId",), "sections")
    for section in section_by_id.values():
        if section.get("studentId") not in ids.get("students", set()):
            conflicts.append(_issue("orphan_reference", "sections", section.get("id")))
    task_by_id = {row.get("id"): row for row in _records(source, "tasks")}
    _validate_positions(conflicts, list(task_by_id.values()), ("studentId", "sectionId"), "tasks")
    for task in task_by_id.values():
        student_id = task.get("studentId")
        if student_id not in ids.get("students", set()):
            conflicts.append(_issue("orphan_reference", "tasks", task.get("id")))
        section_id = task.get("sectionId")
        if section_id and (
            section_id not in section_by_id
            or section_by_id[section_id].get("studentId") != student_id
        ):
            conflicts.append(_issue("orphan_reference", "tasks", task.get("id")))
        study = task.get("studyStatus") or {
            "backlog": "not_started",
            "progress": "in_progress",
            "done": "done",
        }.get(task.get("status"), "not_started")
        if study not in {item.value for item in StudyStatus}:
            conflicts.append(_issue("invalid_task_status", "tasks", task.get("id")))
        if task.get("reviewStatus", "none") not in {item.value for item in ReviewStatus}:
            conflicts.append(_issue("invalid_review_status", "tasks", task.get("id")))
        approval = task.get("approvalStatus")
        if approval is not None and approval not in {item.value for item in ApprovalStatus}:
            conflicts.append(_issue("invalid_approval_status", "tasks", task.get("id")))
        if (
            not isinstance(task.get("title"), str)
            or not task["title"].strip()
            or len(task["title"]) > 255
        ):
            conflicts.append(_issue("invalid_title", "tasks", task.get("id")))
        materials = task.get("materials", [])
        if not isinstance(materials, list):
            conflicts.append(_issue("invalid_collection", "task_materials", task.get("id")))
            materials = []
        if not all(_valid_url(value) for value in [task.get("url"), *materials]):
            conflicts.append(_issue("invalid_url", "tasks", task.get("id")))
    for entity in ("meetings", "homeworks"):
        for record in _records(source, entity):
            if record.get("studentId") not in ids.get("students", set()):
                conflicts.append(_issue("orphan_reference", entity, record.get("id")))
            if (
                not isinstance(record.get("title"), str)
                or not record["title"].strip()
                or len(record["title"]) > 255
            ):
                conflicts.append(_issue("invalid_title", entity, record.get("id")))
    item_count = 0
    for homework in _records(source, "homeworks"):
        if homework.get("status", "draft") not in {item.value for item in HomeworkStatus}:
            conflicts.append(_issue("invalid_homework_status", "homeworks", homework.get("id")))
        homework_items = homework.get("items")
        if not isinstance(homework_items, list):
            continue
        seen_task_ids: set[str] = set()
        for item in homework_items:
            if not isinstance(item, dict):
                continue
            item_count += 1
            task_id = item.get("taskId")
            if task_id in seen_task_ids:
                conflicts.append(_issue("duplicate_id", "homework_items", task_id))
            if isinstance(task_id, str):
                seen_task_ids.add(task_id)
            task = task_by_id.get(item.get("taskId"))
            if task is None or task.get("studentId") != homework.get("studentId"):
                conflicts.append(_issue("orphan_reference", "homework_items", item.get("taskId")))
            materials = item.get("materials", [])
            if not isinstance(materials, list):
                conflicts.append(
                    _issue("invalid_collection", "homework_item_materials", item.get("taskId"))
                )
                materials = []
            if not all(_valid_url(value) for value in [item.get("url"), *materials]):
                conflicts.append(_issue("invalid_url", "homework_items", item.get("taskId")))
        if not _valid_url(homework.get("workUrl")):
            conflicts.append(_issue("invalid_url", "homeworks", homework.get("id")))

    for group in _records(source, "groups"):
        group_id = group.get("id")
        curator_id = payload.curator_assignments.get(str(group_id))
        curator = database.get(User, curator_id) if curator_id else None
        if curator is None or curator.role is not UserRole.ADMIN or not curator.is_active:
            conflicts.append(_issue("invalid_curator_mapping", "groups", group_id))
        group_status = "archived" if group.get("archived") else group.get("status", "active")
        if group_status not in {item.value for item in GroupStatus}:
            conflicts.append(_issue("invalid_group_status", "groups", group_id))
        previous = group.get("statusBeforeArchive")
        if previous is not None and previous not in {"backlog", "active", "completed"}:
            conflicts.append(_issue("invalid_group_status", "groups", group_id))
        if (
            not isinstance(group.get("name"), str)
            or not group["name"].strip()
            or len(group["name"]) > 255
        ):
            conflicts.append(_issue("invalid_title", "groups", group_id))
        try:
            _date(group.get("startsAt"), required=True)
            _date(group.get("endsAt"))
            _date(group.get("actualEndsAt"))
        except (TypeError, ValueError):
            conflicts.append(_issue("invalid_date", "groups", group_id))
        try:
            starts_at = _date(group.get("startsAt"), required=True)
            ends_at = _date(group.get("endsAt"))
            if ends_at is not None and starts_at is not None and ends_at < starts_at:
                raise ValueError
        except (TypeError, ValueError):
            conflicts.append(_issue("invalid_date_order", "groups", group_id))
    for student in _records(source, "students"):
        if (
            not isinstance(student.get("name"), str)
            or not student["name"].strip()
            or len(student["name"]) > 255
        ):
            conflicts.append(_issue("invalid_title", "students", student.get("id")))
        links = student.get("links") or {}
        if not isinstance(links, dict) or not all(_valid_url(value) for value in links.values()):
            conflicts.append(_issue("invalid_url", "students", student.get("id")))
        if student.get("stage", "start") not in {item.value for item in StudentStage}:
            conflicts.append(_issue("invalid_student_stage", "students", student.get("id")))
    for entity, fields in {
        "tasks": ("dueAt", "createdAt", "updatedAt", "archivedAt", "approvalSentAt"),
        "meetings": ("date", "createdAt"),
        "homeworks": (
            "dueAt",
            "issuedAt",
            "submittedAt",
            "reviewedAt",
            "createdAt",
            "deletedAt",
        ),
    }.items():
        for record in _records(source, entity):
            try:
                for field in fields:
                    if field == "date":
                        _date(record.get(field), required=True)
                    else:
                        _datetime(record.get(field))
            except (TypeError, ValueError):
                conflicts.append(_issue("invalid_date", entity, record.get("id")))

    existing = sum(
        database.scalar(select(func.count(model.id))) or 0
        for model in (Group, Student, Strategy, Meeting, Homework)
    )
    completed = database.scalar(select(ImportRun).where(ImportRun.checksum == checksum))
    if existing and completed is None:
        conflicts.append(_issue("server_data_conflict", "database"))
    if any(task.get("history") for task in _records(source, "tasks")):
        warnings.append(
            "Legacy task history has no actor and is preserved in strategy source metadata"
        )
    if any(not task.get("sectionId") for task in _records(source, "tasks")):
        warnings.append(
            "Tasks without a section are placed in a generated technical legacy section"
        )
    warnings.append(
        "IndexedDB knowledge data is not included in AppData and requires a separate export"
    )
    counts = {
        "groups": len(ids.get("groups", set())),
        "students": len(ids.get("students", set())),
        "strategies": len(ids.get("students", set())),
        "sections": len(ids.get("sections", set())),
        "tasks": len(ids.get("tasks", set())),
        "meetings": len(ids.get("meetings", set())),
        "homeworks": len(ids.get("homeworks", set())),
        "homework_items": item_count,
        "approvals": sum(task.get("approvalStatus") is not None for task in task_by_id.values()),
    }
    return ValidationReport(
        valid=not conflicts,
        checksum=checksum,
        source_version=version,
        counts=counts,
        conflicts=conflicts,
        warnings=warnings,
    )


def _mapping(
    database: Session, run: ImportRun, entity_type: str, legacy_id: str, target_id: str
) -> None:
    database.add(
        LegacyIdMapping(
            import_run_id=run.id, entity_type=entity_type, legacy_id=legacy_id, target_id=target_id
        )
    )


def import_legacy(database: Session, actor: User, payload: LegacyImportRequest) -> ImportResult:
    report = validate_legacy(database, actor, payload)
    if not payload.confirm or payload.confirmation_checksum != report.checksum:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "validation_changed",
            "Import confirmation does not match the source",
        )
    previous = database.scalar(select(ImportRun).where(ImportRun.checksum == report.checksum))
    if previous is not None:
        mappings = _mapping_result(database, previous.id)
        return ImportResult(
            import_run_id=previous.id,
            checksum=previous.checksum,
            counts=previous.counts,
            mappings=mappings,
            idempotent_replay=True,
        )
    if not report.valid:
        raise ApiError(
            status.HTTP_409_CONFLICT, "import_conflict", "Legacy data has unresolved conflicts"
        )

    source = payload.source
    run = ImportRun(
        checksum=report.checksum,
        source_version=report.source_version or 0,
        actor_user_id=actor.id,
        counts=report.counts,
    )
    database.add(run)
    database.flush()
    groups: dict[str, Group] = {}
    students: dict[str, Student] = {}
    strategies: dict[str, Strategy] = {}
    sections: dict[str, StrategySection] = {}
    tasks: dict[str, StrategyTask] = {}

    for raw in _records(source, "groups"):
        legacy_id = raw["id"]
        archived = raw.get("archived") or raw.get("status") == "archived"
        group = Group(
            curator_id=payload.curator_assignments[legacy_id],
            curator_role=UserRole.ADMIN,
            name=raw["name"].strip(),
            starts_at=_date(raw.get("startsAt"), required=True),
            ends_at=_date(raw.get("endsAt")),
            actual_ends_at=_date(raw.get("actualEndsAt")),
            status=GroupStatus.ARCHIVED if archived else GroupStatus(raw.get("status") or "active"),
            status_before_archive=GroupStatus(raw.get("statusBeforeArchive") or "completed")
            if archived
            else (
                GroupStatus(raw["statusBeforeArchive"]) if raw.get("statusBeforeArchive") else None
            ),
            notes=raw.get("notes") or "",
            duration_months=raw.get("durationMonths"),
            created_at=_datetime(raw.get("createdAt")) or datetime.now(UTC).replace(tzinfo=None),
        )
        database.add(group)
        database.flush()
        groups[legacy_id] = group
        _mapping(database, run, "group", legacy_id, group.id)
    for raw in _records(source, "students"):
        legacy_id = raw["id"]
        student = Student(
            group_id=groups[raw["groupId"]].id,
            name=(raw.get("name") or "").strip(),
            age=raw.get("age"),
            photo=raw.get("photo") or "",
            avatar_index=raw.get("avatarIndex", -1),
            stage=StudentStage(raw.get("stage") or "start"),
            stage_known=raw.get("stageKnown"),
            starts_at=_date(raw.get("startsAt")),
            level=raw.get("level") or "",
            desired_position=raw.get("desiredPosition") or "",
            career_goal=raw.get("careerGoal") or "",
            links=raw.get("links") or {},
            background=raw.get("background") or "",
            experience=raw.get("experience") or "",
            strengths=raw.get("strengths") or "",
            growth_areas=raw.get("growthAreas") or "",
            difficulties=raw.get("difficulties") or "",
            expectations=raw.get("expectations") or "",
            personal_notes=raw.get("personalNotes") or "",
            point_a=raw.get("pointA") or "",
            point_b=raw.get("pointB") or "",
            notes=raw.get("notes") or "",
            strategy_updated_at=_datetime(raw.get("strategyUpdatedAt"))
            or datetime.now(UTC).replace(tzinfo=None),
            created_at=_datetime(raw.get("createdAt")) or datetime.now(UTC).replace(tzinfo=None),
        )
        database.add(student)
        database.flush()
        students[legacy_id] = student
        _mapping(database, run, "student", legacy_id, student.id)
        metadata = {"legacy_student_id": legacy_id, "legacy_tasks": {}}
        strategy = Strategy(student_id=student.id, source_metadata=metadata)
        database.add(strategy)
        database.flush()
        strategies[legacy_id] = strategy
        _mapping(database, run, "strategy", legacy_id, strategy.id)

    section_rows = list(_records(source, "sections"))
    students_needing_section = {
        task["studentId"] for task in _records(source, "tasks") if not task.get("sectionId")
    }
    for student_id in sorted(students_needing_section):
        generated_id = f"generated:{student_id}:start"
        if not any(row["id"] == generated_id for row in section_rows):
            next_position = 1 + max(
                (
                    int(row.get("order", 0))
                    for row in section_rows
                    if row.get("studentId") == student_id
                ),
                default=-1,
            )
            section_rows.append(
                {
                    "id": generated_id,
                    "studentId": student_id,
                    "title": "Без раздела (legacy)",
                    "order": next_position,
                }
            )
    for raw in section_rows:
        section = StrategySection(
            strategy_id=strategies[raw["studentId"]].id,
            title=(raw.get("title") or "").strip(),
            position=int(raw.get("order", 0)),
            created_at=_datetime(raw.get("createdAt")) or datetime.now(UTC).replace(tzinfo=None),
        )
        database.add(section)
        database.flush()
        sections[raw["id"]] = section
        _mapping(database, run, "section", raw["id"], section.id)
    for raw in _records(source, "tasks"):
        student_id = raw["studentId"]
        section_id = raw.get("sectionId") or f"generated:{student_id}:start"
        status_value = raw.get("studyStatus") or {
            "backlog": "not_started",
            "progress": "in_progress",
            "done": "done",
        }.get(raw.get("status"), "not_started")
        url = raw.get("url") or ""
        task = StrategyTask(
            strategy_id=strategies[student_id].id,
            section_id=sections[section_id].id,
            title=raw["title"].strip(),
            description=raw.get("description") or "",
            materials=raw.get("materials") or [],
            links={"primary": url} if url else {},
            period_text=raw.get("period") or "",
            due_at=_datetime(raw.get("dueAt")),
            position=int(raw.get("order", 0)),
            study_status=StudyStatus(status_value),
            review_status=ReviewStatus(
                raw.get("reviewStatus") or ("accepted" if raw.get("status") == "done" else "none")
            ),
            archived_at=_datetime(raw.get("archivedAt")),
            created_at=_datetime(raw.get("createdAt")) or datetime.now(UTC).replace(tzinfo=None),
            updated_at=_datetime(raw.get("updatedAt")) or datetime.now(UTC).replace(tzinfo=None),
        )
        database.add(task)
        database.flush()
        tasks[raw["id"]] = task
        _mapping(database, run, "task", raw["id"], task.id)
        strategy_metadata = dict(strategies[student_id].source_metadata)
        legacy_tasks = dict(strategy_metadata["legacy_tasks"])
        legacy_tasks[raw["id"]] = {
            "comments": raw.get("comments") or "",
            "history": raw.get("history") or [],
            "owner": raw.get("owner"),
            "approval_type": raw.get("approvalType") or "",
            "stage": raw.get("stage"),
            "blocker": raw.get("blocker", False),
            "source_file": raw.get("sourceFile"),
        }
        strategy_metadata["legacy_tasks"] = legacy_tasks
        strategies[student_id].source_metadata = strategy_metadata
        if raw.get("approvalStatus") is not None:
            database.add(
                AnyaApproval(
                    task_id=task.id,
                    status=ApprovalStatus(raw["approvalStatus"]),
                    comment=raw.get("approvalComment") or "",
                    created_at=_datetime(raw.get("approvalSentAt")) or task.created_at,
                )
            )
    for raw in _records(source, "meetings"):
        meeting = Meeting(
            student_id=students[raw["studentId"]].id,
            date=_date(raw.get("date"), required=True),
            title=raw["title"].strip(),
            summary=raw.get("summary") or "",
            created_at=_datetime(raw.get("createdAt")) or datetime.now(UTC).replace(tzinfo=None),
        )
        database.add(meeting)
        database.flush()
        _mapping(database, run, "meeting", raw["id"], meeting.id)
    for raw in _records(source, "homeworks"):
        strategy = strategies[raw["studentId"]]
        homework = Homework(
            strategy_id=strategy.id,
            title=raw["title"].strip(),
            description=raw.get("text") or "",
            submission_links={"work": raw["workUrl"]} if raw.get("workUrl") else {},
            curator_feedback=raw.get("comment") or "",
            due_at=_datetime(raw.get("dueAt")),
            status=HomeworkStatus(raw.get("status") or "draft"),
            issued_at=_datetime(raw.get("issuedAt")),
            submitted_at=_datetime(raw.get("submittedAt")),
            reviewed_at=_datetime(raw.get("reviewedAt")),
            archived_at=_datetime(raw.get("deletedAt")),
            created_at=_datetime(raw.get("createdAt")) or datetime.now(UTC).replace(tzinfo=None),
        )
        database.add(homework)
        database.flush()
        _mapping(database, run, "homework", raw["id"], homework.id)
        for position, item in enumerate(raw.get("items") or []):
            task = tasks[item["taskId"]]
            item_url = item.get("url") or ""
            database.add(
                HomeworkItem(
                    homework_id=homework.id,
                    strategy_id=strategy.id,
                    task_id=task.id,
                    position=position,
                    title=item.get("title") or task.title,
                    description=item.get("description") or "",
                    materials=item.get("materials") or [],
                    links={"primary": item_url} if item_url else {},
                    due_at=_datetime(item.get("dueAt")),
                )
            )
    record_audit(
        database,
        actor=actor,
        action=AuditAction.LEGACY_IMPORTED,
        details={"import_run_id": run.id, "checksum": run.checksum, "counts": report.counts},
    )
    database.flush()
    return ImportResult(
        import_run_id=run.id,
        checksum=run.checksum,
        counts=run.counts,
        mappings=_mapping_result(database, run.id),
        idempotent_replay=False,
    )


def _mapping_result(database: Session, run_id: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in database.scalars(
        select(LegacyIdMapping)
        .where(LegacyIdMapping.import_run_id == run_id)
        .order_by(LegacyIdMapping.entity_type, LegacyIdMapping.legacy_id)
    ):
        result.setdefault(row.entity_type, {})[row.legacy_id] = row.target_id
    return result


def _value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def export_backup(database: Session, actor: User, exported_at: datetime) -> dict[str, Any]:
    ensure_owner(actor)
    models = (
        Group,
        Student,
        Strategy,
        StrategySection,
        StrategyTask,
        AnyaApproval,
        TaskHistory,
        Meeting,
        Homework,
        HomeworkItem,
        HomeworkHistory,
        AuditEvent,
        ImportRun,
        LegacyIdMapping,
    )
    data: dict[str, list[dict[str, Any]]] = {}
    for model in models:
        rows = database.scalars(select(model).order_by(model.id)).all()
        data[model.__tablename__] = [
            {column.name: _value(getattr(row, column.name)) for column in model.__table__.columns}
            for row in rows
        ]
    return {
        "schema": "kuratorskaya-backup",
        "version": 1,
        "exported_at": exported_at.isoformat(),
        "limitations": [
            "Authentication accounts and secrets are excluded",
            "IndexedDB knowledge data requires a separate browser export",
            "Restore requires matching curator and history actor accounts",
        ],
        "data": data,
    }


RESTORE_ORDER = (
    Group,
    Student,
    Strategy,
    StrategySection,
    StrategyTask,
    AnyaApproval,
    TaskHistory,
    Meeting,
    Homework,
    HomeworkItem,
    HomeworkHistory,
    ImportRun,
    LegacyIdMapping,
    AuditEvent,
)


def restore_backup(database: Session, backup: dict[str, Any]) -> dict[str, int]:
    if backup.get("schema") != "kuratorskaya-backup" or backup.get("version") != 1:
        raise ValueError("Unsupported backup format")
    data = backup.get("data")
    if not isinstance(data, dict):
        raise ValueError("Invalid backup data")
    existing = sum(
        database.scalar(select(func.count(model.id))) or 0
        for model in (Group, Student, Strategy, Meeting, Homework, ImportRun)
    )
    if existing:
        raise ValueError("Restore target already contains business data")
    required_user_ids = {
        row[field]
        for table, field in (
            ("groups", "curator_id"),
            ("task_history", "actor_user_id"),
            ("homework_history", "actor_user_id"),
            ("import_runs", "actor_user_id"),
            ("audit_events", "actor_user_id"),
            ("audit_events", "target_user_id"),
        )
        for row in data.get(table, [])
        if isinstance(row, dict) and row.get(field)
    }
    existing_user_ids = set(database.scalars(select(User.id).where(User.id.in_(required_user_ids))))
    if existing_user_ids != required_user_ids:
        raise ValueError("Restore requires matching users before business data")
    counts: dict[str, int] = {}
    for model in RESTORE_ORDER:
        table = model.__tablename__
        rows = data.get(table, [])
        if not isinstance(rows, list):
            raise ValueError(f"Invalid {table} collection")
        allowed = {column.name: column for column in model.__table__.columns}
        for raw in rows:
            if not isinstance(raw, dict) or set(raw) != set(raw) & allowed.keys():
                raise ValueError(f"Invalid {table} record")
            values: dict[str, Any] = {}
            for key, value in raw.items():
                column = allowed[key]
                if value is not None and isinstance(column.type, DateTime):
                    value = _datetime(value)
                elif value is not None and isinstance(column.type, Date):
                    value = _date(value)
                values[key] = value
            database.add(model(**values))
        database.flush()
        counts[table] = len(rows)
    return counts
