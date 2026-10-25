from __future__ import annotations

from datetime import datetime

from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.pagination import decode_cursor, encode_cursor
from app.modules.auth.authorization import is_owner
from app.modules.groups.models import Group, GroupStatus
from app.modules.students.models import Student
from app.modules.students.schemas import StudentCreate, StudentUpdate
from app.modules.users.audit import AuditAction
from app.modules.users.models import User
from app.modules.users.service import ensure_admin, record_audit


def _conflict(code: str, message: str) -> ApiError:
    return ApiError(status.HTTP_409_CONFLICT, code, message)


def list_students(
    database: Session,
    actor: User,
    group: Group,
    *,
    cursor: str | None,
    limit: int,
) -> tuple[list[Student], str | None]:
    ensure_admin(actor)
    statement = select(Student).where(Student.group_id == group.id)
    cursor_id = decode_cursor(cursor)
    if cursor_id is not None:
        statement = statement.where(Student.id > cursor_id)
    students = list(database.scalars(statement.order_by(Student.id).limit(limit + 1)))
    has_more = len(students) > limit
    items = students[:limit]
    return items, encode_cursor(items[-1].id) if has_more else None


def _lock_group_for_student_creation(database: Session, actor: User, group: Group) -> None:
    statement = update(Group).where(
        Group.id == group.id,
        Group.status != GroupStatus.ARCHIVED,
    )
    if not is_owner(actor):
        statement = statement.where(Group.curator_id == actor.id)
    result = database.execute(
        statement.values(version=Group.version).execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        database.rollback()
        raise _conflict("group_changed", "Group is archived or its curator assignment changed")


def create_student(
    database: Session,
    actor: User,
    group: Group,
    payload: StudentCreate,
) -> Student:
    _lock_group_for_student_creation(database, actor, group)
    values = payload.model_dump()
    values["links"] = {key: str(value) for key, value in payload.links.items()}
    student = Student(group_id=group.id, **values)
    database.add(student)
    database.flush()
    record_audit(
        database,
        actor=actor,
        action=AuditAction.STUDENT_CREATED,
        target_group_id=group.id,
        details={"student_id": student.id},
    )
    return student


def _student_scope(statement, actor: User, student: Student):
    if is_owner(actor):
        return statement
    return statement.where(
        Student.group_id.in_(select(Group.id).where(Group.curator_id == actor.id)),
        Student.group_id == student.group_id,
    )


def _refresh_or_conflict(database: Session, student: Student, rowcount: int) -> Student:
    if rowcount != 1:
        database.rollback()
        raise _conflict("version_conflict", "Student was changed by another request")
    database.refresh(student)
    return student


def update_student(
    database: Session,
    actor: User,
    student: Student,
    payload: StudentUpdate,
    now: datetime,
) -> Student:
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if "links" in values:
        incoming = {key: str(value) for key, value in (payload.links or {}).items()}
        values["links"] = {**student.links, **incoming}
    statement = update(Student).where(
        Student.id == student.id,
        Student.version == payload.expected_version,
    )
    result = database.execute(
        _student_scope(statement, actor, student)
        .values(**values, version=Student.version + 1, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    _refresh_or_conflict(database, student, result.rowcount)
    record_audit(
        database,
        actor=actor,
        action=AuditAction.STUDENT_UPDATED,
        target_group_id=student.group_id,
        details={"student_id": student.id, "fields": sorted(values)},
    )
    return student


def archive_student(
    database: Session,
    actor: User,
    student: Student,
    expected_version: int,
    now: datetime,
) -> Student:
    if student.archived_at is not None:
        raise _conflict("invalid_student_transition", "Student is already archived")
    statement = update(Student).where(
        Student.id == student.id,
        Student.version == expected_version,
        Student.archived_at.is_(None),
    )
    result = database.execute(
        _student_scope(statement, actor, student)
        .values(archived_at=now, version=Student.version + 1, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    _refresh_or_conflict(database, student, result.rowcount)
    record_audit(
        database,
        actor=actor,
        action=AuditAction.STUDENT_ARCHIVED,
        target_group_id=student.group_id,
        details={"student_id": student.id},
    )
    return student


def restore_student(
    database: Session,
    actor: User,
    student: Student,
    expected_version: int,
    now: datetime,
) -> Student:
    if student.archived_at is None:
        raise _conflict("invalid_student_transition", "Student is not archived")
    statement = update(Student).where(
        Student.id == student.id,
        Student.version == expected_version,
        Student.archived_at.is_not(None),
    )
    result = database.execute(
        _student_scope(statement, actor, student)
        .values(archived_at=None, version=Student.version + 1, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    _refresh_or_conflict(database, student, result.rowcount)
    record_audit(
        database,
        actor=actor,
        action=AuditAction.STUDENT_RESTORED,
        target_group_id=student.group_id,
        details={"student_id": student.id},
    )
    return student
