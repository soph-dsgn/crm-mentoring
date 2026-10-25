from __future__ import annotations

from datetime import datetime

from fastapi import status
from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.pagination import decode_cursor, encode_cursor
from app.modules.auth.authorization import can_read_student, can_update_student
from app.modules.groups.models import Group
from app.modules.meetings.models import Meeting
from app.modules.meetings.schemas import MeetingCreate, MeetingUpdate
from app.modules.students.models import Student
from app.modules.users.audit import AuditAction
from app.modules.users.models import User
from app.modules.users.service import record_audit


def _not_found(resource: str) -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, "not_found", f"{resource} not found")


def _forbidden() -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, "forbidden", "Operation not permitted")


def _conflict(code: str, message: str) -> ApiError:
    return ApiError(status.HTTP_409_CONFLICT, code, message)


def get_student(database: Session, actor: User, student_id: str, *, write: bool) -> Student:
    student = database.get(Student, student_id)
    if student is None or not can_read_student(actor, student):
        raise _not_found("Student")
    if write and not can_update_student(actor, student):
        raise _forbidden()
    return student


def _write_scope(student_id: str, actor: User):
    statement = (
        select(Student.id).join(Group, Student.group_id == Group.id).where(Student.id == student_id)
    )
    if not actor.is_owner:
        statement = statement.where(Group.curator_id == actor.id)
    return exists(statement)


def get_meeting(database: Session, actor: User, meeting_id: str, *, write: bool) -> Meeting:
    meeting = database.get(Meeting, meeting_id)
    if meeting is None:
        raise _not_found("Meeting")
    get_student(database, actor, meeting.student_id, write=write)
    return meeting


def list_meetings(
    database: Session,
    student: Student,
    *,
    cursor: str | None,
    limit: int,
    include_archived: bool,
) -> tuple[list[Meeting], str | None]:
    statement = select(Meeting).where(Meeting.student_id == student.id)
    if not include_archived:
        statement = statement.where(Meeting.archived_at.is_(None))
    cursor_id = decode_cursor(cursor)
    if cursor_id is not None:
        row = database.get(Meeting, cursor_id)
        if row is None or row.student_id != student.id:
            raise ApiError(422, "invalid_cursor", "Pagination cursor is invalid")
        statement = statement.where(
            or_(Meeting.date < row.date, and_(Meeting.date == row.date, Meeting.id > row.id))
        )
    rows = list(
        database.scalars(statement.order_by(Meeting.date.desc(), Meeting.id).limit(limit + 1))
    )
    items = rows[:limit]
    return items, encode_cursor(items[-1].id) if len(rows) > limit else None


def create_meeting(
    database: Session,
    actor: User,
    student: Student,
    payload: MeetingCreate,
) -> Meeting:
    result = database.execute(
        update(Student)
        .where(Student.id == student.id, _write_scope(student.id, actor))
        .values(version=Student.version)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        database.rollback()
        raise _conflict("curator_assignment_changed", "Curator assignment changed")
    meeting = Meeting(student_id=student.id, **payload.model_dump())
    database.add(meeting)
    database.flush()
    record_audit(
        database,
        actor=actor,
        action=AuditAction.MEETING_CREATED,
        target_group_id=student.group_id,
        details={"meeting_id": meeting.id, "student_id": student.id},
    )
    return meeting


def update_meeting(
    database: Session,
    actor: User,
    meeting: Meeting,
    payload: MeetingUpdate,
    now: datetime,
) -> Meeting:
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    result = database.execute(
        update(Meeting)
        .where(
            Meeting.id == meeting.id,
            Meeting.version == payload.expected_version,
            _write_scope(meeting.student_id, actor),
        )
        .values(**values, version=Meeting.version + 1, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        database.rollback()
        raise _conflict("version_conflict", "Meeting changed by another request")
    database.refresh(meeting)
    student = database.get(Student, meeting.student_id)
    record_audit(
        database,
        actor=actor,
        action=AuditAction.MEETING_UPDATED,
        target_group_id=student.group_id,
        details={"meeting_id": meeting.id, "fields": sorted(values)},
    )
    return meeting


def set_meeting_archived(
    database: Session,
    actor: User,
    meeting: Meeting,
    expected_version: int,
    now: datetime,
    *,
    archived: bool,
) -> Meeting:
    if archived == (meeting.archived_at is not None):
        raise _conflict(
            "invalid_meeting_transition",
            "Meeting is already archived" if archived else "Meeting is not archived",
        )
    result = database.execute(
        update(Meeting)
        .where(
            Meeting.id == meeting.id,
            Meeting.version == expected_version,
            _write_scope(meeting.student_id, actor),
        )
        .values(
            archived_at=now if archived else None,
            version=Meeting.version + 1,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        database.rollback()
        raise _conflict("version_conflict", "Meeting changed by another request")
    database.refresh(meeting)
    student = database.get(Student, meeting.student_id)
    record_audit(
        database,
        actor=actor,
        action=AuditAction.MEETING_ARCHIVED if archived else AuditAction.MEETING_RESTORED,
        target_group_id=student.group_id,
        details={"meeting_id": meeting.id},
    )
    return meeting
