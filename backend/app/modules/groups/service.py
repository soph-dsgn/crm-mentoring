from __future__ import annotations

from datetime import datetime

from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.pagination import decode_cursor, encode_cursor
from app.modules.auth.authorization import curator_for_new_group, is_owner
from app.modules.groups.models import Group, GroupStatus
from app.modules.groups.schemas import GroupCreate, GroupUpdate
from app.modules.students.models import Student
from app.modules.users.audit import AuditAction
from app.modules.users.models import User, UserRole
from app.modules.users.service import record_audit


def _conflict(code: str, message: str) -> ApiError:
    return ApiError(status.HTTP_409_CONFLICT, code, message)


def list_groups(
    database: Session,
    actor: User,
    *,
    lifecycle: GroupStatus | None,
    curator_id: str | None,
    cursor: str | None,
    limit: int,
) -> tuple[list[Group], str | None]:
    statement = select(Group)
    if actor.role is UserRole.STUDENT:
        statement = statement.join(Student).where(Student.user_id == actor.id)
    if lifecycle is not None:
        statement = statement.where(Group.status == lifecycle)
    if curator_id is not None and actor.role is UserRole.ADMIN:
        statement = statement.where(Group.curator_id == curator_id)
    cursor_id = decode_cursor(cursor)
    if cursor_id is not None:
        statement = statement.where(Group.id > cursor_id)
    groups = list(database.scalars(statement.order_by(Group.id).limit(limit + 1)))
    has_more = len(groups) > limit
    items = groups[:limit]
    return items, encode_cursor(items[-1].id) if has_more else None


def create_group(database: Session, actor: User, payload: GroupCreate) -> Group:
    curator = curator_for_new_group(actor)
    group = Group(
        curator_id=curator.id,
        curator_role=UserRole.ADMIN,
        **payload.model_dump(),
    )
    database.add(group)
    database.flush()
    record_audit(
        database,
        actor=actor,
        action=AuditAction.GROUP_CREATED,
        target_group_id=group.id,
    )
    return group


def _scope(statement, actor: User, group: Group):
    if is_owner(actor):
        return statement
    return statement.where(Group.curator_id == actor.id, Group.curator_id == group.curator_id)


def _refresh_or_conflict(database: Session, group: Group, rowcount: int) -> Group:
    if rowcount != 1:
        database.rollback()
        raise _conflict("version_conflict", "Group was changed by another request")
    database.refresh(group)
    return group


def update_group(
    database: Session,
    actor: User,
    group: Group,
    payload: GroupUpdate,
    now: datetime,
) -> Group:
    if group.status is GroupStatus.ARCHIVED:
        raise _conflict("group_archived", "Restore the group before editing it")
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    starts_at = values.get("starts_at", group.starts_at)
    ends_at = values.get("ends_at", group.ends_at)
    actual_ends_at = values.get("actual_ends_at", group.actual_ends_at)
    invalid_field = next(
        (
            field
            for field, value in (("ends_at", ends_at), ("actual_ends_at", actual_ends_at))
            if value is not None and starts_at > value
        ),
        None,
    )
    if invalid_field is not None:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_dates",
            f"{invalid_field} must not precede starts_at",
        )
    statement = update(Group).where(
        Group.id == group.id,
        Group.version == payload.expected_version,
    )
    statement = _scope(statement, actor, group)
    result = database.execute(
        statement.values(**values, version=Group.version + 1, updated_at=now).execution_options(
            synchronize_session=False
        )
    )
    _refresh_or_conflict(database, group, result.rowcount)
    record_audit(
        database,
        actor=actor,
        action=AuditAction.GROUP_UPDATED,
        target_group_id=group.id,
        details={"fields": sorted(values)},
    )
    return group


def archive_group(
    database: Session,
    actor: User,
    group: Group,
    expected_version: int,
    now: datetime,
) -> Group:
    if group.status is GroupStatus.ARCHIVED:
        raise _conflict("invalid_group_transition", "Group is already archived")
    statement = update(Group).where(Group.id == group.id, Group.version == expected_version)
    result = database.execute(
        _scope(statement, actor, group)
        .values(
            status_before_archive=group.status,
            status=GroupStatus.ARCHIVED,
            version=Group.version + 1,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    _refresh_or_conflict(database, group, result.rowcount)
    record_audit(
        database,
        actor=actor,
        action=AuditAction.GROUP_ARCHIVED,
        target_group_id=group.id,
    )
    return group


def restore_group(
    database: Session,
    actor: User,
    group: Group,
    expected_version: int,
    now: datetime,
) -> Group:
    if group.status is not GroupStatus.ARCHIVED:
        raise _conflict("invalid_group_transition", "Group is not archived")
    restored_status = group.status_before_archive or GroupStatus.BACKLOG
    statement = update(Group).where(Group.id == group.id, Group.version == expected_version)
    result = database.execute(
        _scope(statement, actor, group)
        .values(
            status=restored_status,
            status_before_archive=None,
            version=Group.version + 1,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    _refresh_or_conflict(database, group, result.rowcount)
    record_audit(
        database,
        actor=actor,
        action=AuditAction.GROUP_RESTORED,
        target_group_id=group.id,
    )
    return group
