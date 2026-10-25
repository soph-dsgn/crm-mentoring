from __future__ import annotations

from datetime import datetime

from fastapi import status
from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.pagination import decode_cursor, encode_cursor
from app.modules.auth.authorization import can_read_student, can_update_student, is_owner
from app.modules.auth.dependencies import utc_now
from app.modules.groups.models import Group
from app.modules.strategies.models import (
    AnyaApproval,
    ApprovalStatus,
    Strategy,
    StrategySection,
    StrategyTask,
    StudyStatus,
    TaskHistory,
)
from app.modules.strategies.schemas import (
    ApprovalCreate,
    ApprovalTransition,
    SectionCreate,
    SectionReorder,
    SectionUpdate,
    StrategyCreate,
    TaskCreate,
    TaskStatusChange,
    TaskUpdate,
)
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


def get_student_for_strategy(
    database: Session, actor: User, student_id: str, *, write: bool
) -> Student:
    student = database.get(Student, student_id)
    if student is None or not can_read_student(actor, student):
        raise _not_found("Student")
    if write and not can_update_student(actor, student):
        raise _forbidden()
    return student


def get_strategy_for_student(database: Session, student_id: str) -> Strategy:
    strategy = database.scalar(select(Strategy).where(Strategy.student_id == student_id))
    if strategy is None:
        raise _not_found("Strategy")
    return strategy


def get_strategy(database: Session, actor: User, strategy_id: str, *, write: bool) -> Strategy:
    strategy = database.get(Strategy, strategy_id)
    if strategy is None:
        raise _not_found("Strategy")
    student = database.get(Student, strategy.student_id)
    if student is None or not can_read_student(actor, student):
        raise _not_found("Strategy")
    if write and not can_update_student(actor, student):
        raise _forbidden()
    return strategy


def get_section(database: Session, actor: User, section_id: str, *, write: bool) -> StrategySection:
    section = database.get(StrategySection, section_id)
    if section is None:
        raise _not_found("Strategy section")
    get_strategy(database, actor, section.strategy_id, write=write)
    return section


def get_task(database: Session, actor: User, task_id: str, *, write: bool) -> StrategyTask:
    task = database.get(StrategyTask, task_id)
    if task is None:
        raise _not_found("Strategy task")
    get_strategy(database, actor, task.strategy_id, write=write)
    return task


def _group_id(database: Session, strategy_id: str) -> str:
    group_id = database.scalar(
        select(Student.group_id)
        .join(Strategy, Strategy.student_id == Student.id)
        .where(Strategy.id == strategy_id)
    )
    if group_id is None:
        raise _not_found("Strategy")
    return group_id


def _write_scope(strategy_id: str, actor: User):
    statement = (
        select(Strategy.id)
        .join(Student, Strategy.student_id == Student.id)
        .join(Group, Student.group_id == Group.id)
        .where(Strategy.id == strategy_id)
    )
    if not actor.is_owner:
        statement = statement.where(Group.curator_id == actor.id)
    return exists(statement)


def _lock_strategy_write(database: Session, strategy: Strategy, actor: User) -> None:
    result = database.execute(
        update(Strategy)
        .where(Strategy.id == strategy.id, _write_scope(strategy.id, actor))
        .values(version=Strategy.version)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        database.rollback()
        raise _conflict("curator_assignment_changed", "Curator assignment changed")


def _history(
    database: Session,
    *,
    task_id: str,
    actor: User,
    event_type: str,
    details: dict[str, object] | None = None,
) -> None:
    database.add(
        TaskHistory(
            task_id=task_id,
            actor_user_id=actor.id,
            event_type=event_type,
            details=details or {},
            created_at=utc_now(),
        )
    )


def create_strategy(
    database: Session,
    actor: User,
    student: Student,
    payload: StrategyCreate,
) -> Strategy:
    statement = update(Group).where(Group.id == student.group_id)
    if not is_owner(actor):
        statement = statement.where(Group.curator_id == actor.id)
    result = database.execute(
        statement.values(version=Group.version).execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        database.rollback()
        raise _conflict("curator_assignment_changed", "Curator assignment changed")
    if database.scalar(select(Strategy.id).where(Strategy.student_id == student.id)) is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "strategy_exists",
            "Student already has a strategy",
        )
    strategy = Strategy(student_id=student.id, source_metadata=payload.source_metadata)
    database.add(strategy)
    database.flush()
    record_audit(
        database,
        actor=actor,
        action=AuditAction.STRATEGY_CREATED,
        target_group_id=student.group_id,
        details={"strategy_id": strategy.id, "student_id": student.id},
    )
    return strategy


def list_sections(database: Session, strategy: Strategy) -> list[StrategySection]:
    return list(
        database.scalars(
            select(StrategySection)
            .where(StrategySection.strategy_id == strategy.id)
            .order_by(StrategySection.position, StrategySection.id)
        )
    )


def create_section(
    database: Session,
    actor: User,
    strategy: Strategy,
    payload: SectionCreate,
) -> StrategySection:
    _lock_strategy_write(database, strategy, actor)
    section = StrategySection(strategy_id=strategy.id, **payload.model_dump())
    database.add(section)
    database.flush()
    record_audit(
        database,
        actor=actor,
        action=AuditAction.SECTION_CREATED,
        target_group_id=_group_id(database, strategy.id),
        details={"strategy_id": strategy.id, "section_id": section.id},
    )
    return section


def update_section(
    database: Session,
    actor: User,
    section: StrategySection,
    payload: SectionUpdate,
    now: datetime,
) -> StrategySection:
    result = database.execute(
        update(StrategySection)
        .where(
            StrategySection.id == section.id,
            StrategySection.version == payload.expected_version,
            _write_scope(section.strategy_id, actor),
        )
        .values(title=payload.title, version=StrategySection.version + 1, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        database.rollback()
        raise _conflict("version_conflict", "Strategy section changed by another request")
    database.refresh(section)
    record_audit(
        database,
        actor=actor,
        action=AuditAction.SECTION_UPDATED,
        target_group_id=_group_id(database, section.strategy_id),
        details={"strategy_id": section.strategy_id, "section_id": section.id},
    )
    return section


def reorder_sections(
    database: Session,
    actor: User,
    strategy: Strategy,
    payload: SectionReorder,
    now: datetime,
) -> list[StrategySection]:
    _lock_strategy_write(database, strategy, actor)
    sections = list_sections(database, strategy)
    item_by_id = {item.id: item for item in payload.items}
    if len(item_by_id) != len(payload.items) or set(item_by_id) != {item.id for item in sections}:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_reorder",
            "Reorder must include every section exactly once",
        )
    if len({item.position for item in payload.items}) != len(payload.items):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_reorder",
            "Section positions must be unique",
        )
    temporary_base = max(
        [section.position for section in sections] + [item.position for item in payload.items] + [0]
    ) + len(sections)
    for index, section in enumerate(sections, start=1):
        item = item_by_id[section.id]
        result = database.execute(
            update(StrategySection)
            .where(
                StrategySection.id == section.id, StrategySection.version == item.expected_version
            )
            .values(
                position=temporary_base + index,
                version=StrategySection.version + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            database.rollback()
            raise _conflict("version_conflict", "Strategy section changed by another request")
    database.flush()
    for section in sections:
        database.execute(
            update(StrategySection)
            .where(StrategySection.id == section.id)
            .values(position=item_by_id[section.id].position)
        )
    record_audit(
        database,
        actor=actor,
        action=AuditAction.SECTIONS_REORDERED,
        target_group_id=_group_id(database, strategy.id),
        details={"strategy_id": strategy.id, "section_ids": sorted(item_by_id)},
    )
    database.flush()
    database.expire_all()
    return list_sections(database, strategy)


def create_task(
    database: Session,
    actor: User,
    section: StrategySection,
    payload: TaskCreate,
) -> StrategyTask:
    strategy = database.get(Strategy, section.strategy_id)
    if strategy is None:
        raise _not_found("Strategy")
    _lock_strategy_write(database, strategy, actor)
    values = payload.model_dump()
    values["links"] = {key: str(value) for key, value in payload.links.items()}
    task = StrategyTask(strategy_id=section.strategy_id, section_id=section.id, **values)
    database.add(task)
    database.flush()
    _history(database, task_id=task.id, actor=actor, event_type="task_created")
    record_audit(
        database,
        actor=actor,
        action=AuditAction.TASK_CREATED,
        target_group_id=_group_id(database, task.strategy_id),
        details={"strategy_id": task.strategy_id, "section_id": section.id, "task_id": task.id},
    )
    return task


def list_tasks(
    database: Session, section: StrategySection, *, include_archived: bool
) -> list[StrategyTask]:
    statement = select(StrategyTask).where(StrategyTask.section_id == section.id)
    if not include_archived:
        statement = statement.where(StrategyTask.archived_at.is_(None))
    return list(database.scalars(statement.order_by(StrategyTask.position, StrategyTask.id)))


def reorder_tasks(
    database: Session,
    actor: User,
    section: StrategySection,
    payload: SectionReorder,
    now: datetime,
) -> list[StrategyTask]:
    strategy = database.get(Strategy, section.strategy_id)
    if strategy is None:
        raise _not_found("Strategy")
    _lock_strategy_write(database, strategy, actor)
    tasks = list_tasks(database, section, include_archived=True)
    item_by_id = {item.id: item for item in payload.items}
    if len(item_by_id) != len(payload.items) or set(item_by_id) != {item.id for item in tasks}:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_reorder",
            "Reorder must include every task exactly once",
        )
    if len({item.position for item in payload.items}) != len(payload.items):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_reorder",
            "Task positions must be unique",
        )
    temporary_base = max(
        [task.position for task in tasks] + [item.position for item in payload.items] + [0]
    ) + len(tasks)
    for index, task in enumerate(tasks, start=1):
        item = item_by_id[task.id]
        result = database.execute(
            update(StrategyTask)
            .where(StrategyTask.id == task.id, StrategyTask.version == item.expected_version)
            .values(
                position=temporary_base + index,
                version=StrategyTask.version + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            database.rollback()
            raise _conflict("version_conflict", "Strategy task changed by another request")
    database.flush()
    for task in tasks:
        database.execute(
            update(StrategyTask)
            .where(StrategyTask.id == task.id)
            .values(position=item_by_id[task.id].position)
        )
        _history(
            database,
            task_id=task.id,
            actor=actor,
            event_type="task_reordered",
            details={"position": item_by_id[task.id].position},
        )
    record_audit(
        database,
        actor=actor,
        action=AuditAction.TASK_UPDATED,
        target_group_id=_group_id(database, section.strategy_id),
        details={"section_id": section.id, "task_ids": sorted(item_by_id), "fields": ["position"]},
    )
    database.flush()
    database.expire_all()
    return list_tasks(database, section, include_archived=True)


def _update_task_row(
    database: Session,
    actor: User,
    task: StrategyTask,
    expected_version: int,
    values: dict[str, object],
    now: datetime,
) -> StrategyTask:
    result = database.execute(
        update(StrategyTask)
        .where(
            StrategyTask.id == task.id,
            StrategyTask.version == expected_version,
            _write_scope(task.strategy_id, actor),
        )
        .values(**values, version=StrategyTask.version + 1, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        database.rollback()
        raise _conflict("version_conflict", "Strategy task changed by another request")
    database.refresh(task)
    return task


def update_task(
    database: Session,
    actor: User,
    task: StrategyTask,
    payload: TaskUpdate,
    now: datetime,
) -> StrategyTask:
    if task.archived_at is not None:
        raise _conflict("task_archived", "Restore the task before editing it")
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if "links" in values:
        values["links"] = {key: str(value) for key, value in payload.links.items()}
    _update_task_row(database, actor, task, payload.expected_version, values, now)
    _history(
        database,
        task_id=task.id,
        actor=actor,
        event_type="task_updated",
        details={"fields": sorted(values)},
    )
    record_audit(
        database,
        actor=actor,
        action=AuditAction.TASK_UPDATED,
        target_group_id=_group_id(database, task.strategy_id),
        details={"task_id": task.id, "fields": sorted(values)},
    )
    return task


STUDY_TRANSITIONS = {
    StudyStatus.NOT_STARTED: {StudyStatus.IN_PROGRESS, StudyStatus.HOLD},
    StudyStatus.IN_PROGRESS: {StudyStatus.HOLD, StudyStatus.DONE},
    StudyStatus.HOLD: {StudyStatus.IN_PROGRESS, StudyStatus.DONE},
    StudyStatus.DONE: {StudyStatus.IN_PROGRESS},
}


def change_task_status(
    database: Session,
    actor: User,
    task: StrategyTask,
    payload: TaskStatusChange,
    now: datetime,
) -> StrategyTask:
    if task.archived_at is not None:
        raise _conflict("task_archived", "Restore the task before changing its status")
    if payload.study_status not in STUDY_TRANSITIONS[task.study_status]:
        raise _conflict("invalid_status_transition", "Study status transition is not allowed")
    previous = task.study_status
    _update_task_row(
        database,
        actor,
        task,
        payload.expected_version,
        {"study_status": payload.study_status},
        now,
    )
    _history(
        database,
        task_id=task.id,
        actor=actor,
        event_type="study_status_changed",
        details={"from": previous.value, "to": payload.study_status.value},
    )
    record_audit(
        database,
        actor=actor,
        action=AuditAction.TASK_STATUS_CHANGED,
        target_group_id=_group_id(database, task.strategy_id),
        details={"task_id": task.id, "from": previous.value, "to": payload.study_status.value},
    )
    return task


def set_task_archived(
    database: Session,
    actor: User,
    task: StrategyTask,
    expected_version: int,
    now: datetime,
    *,
    archived: bool,
) -> StrategyTask:
    if archived == (task.archived_at is not None):
        raise _conflict(
            "invalid_task_transition",
            "Task is already archived" if archived else "Task is not archived",
        )
    _update_task_row(
        database,
        actor,
        task,
        expected_version,
        {"archived_at": now if archived else None},
        now,
    )
    event_type = "task_archived" if archived else "task_restored"
    _history(database, task_id=task.id, actor=actor, event_type=event_type)
    record_audit(
        database,
        actor=actor,
        action=AuditAction.TASK_ARCHIVED if archived else AuditAction.TASK_RESTORED,
        target_group_id=_group_id(database, task.strategy_id),
        details={"task_id": task.id},
    )
    return task


def list_history(
    database: Session,
    task: StrategyTask,
    *,
    cursor: str | None,
    limit: int,
) -> tuple[list[TaskHistory], str | None]:
    statement = select(TaskHistory).where(TaskHistory.task_id == task.id)
    cursor_id = decode_cursor(cursor)
    if cursor_id is not None:
        cursor_row = database.get(TaskHistory, cursor_id)
        if cursor_row is None or cursor_row.task_id != task.id:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "invalid_cursor",
                "Pagination cursor is invalid",
            )
        statement = statement.where(
            or_(
                TaskHistory.created_at > cursor_row.created_at,
                and_(
                    TaskHistory.created_at == cursor_row.created_at,
                    TaskHistory.id > cursor_row.id,
                ),
            )
        )
    rows = list(
        database.scalars(
            statement.order_by(TaskHistory.created_at, TaskHistory.id).limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    items = rows[:limit]
    return items, encode_cursor(items[-1].id) if has_more else None


def get_approval(database: Session, task: StrategyTask) -> AnyaApproval:
    approval = database.scalar(select(AnyaApproval).where(AnyaApproval.task_id == task.id))
    if approval is None:
        raise _not_found("Anya approval")
    return approval


def create_approval(
    database: Session,
    actor: User,
    task: StrategyTask,
    payload: ApprovalCreate,
) -> AnyaApproval:
    if database.scalar(select(AnyaApproval.id).where(AnyaApproval.task_id == task.id)) is not None:
        raise _conflict("approval_exists", "Task already has an approval")
    strategy = database.get(Strategy, task.strategy_id)
    if strategy is None:
        raise _not_found("Strategy")
    _lock_strategy_write(database, strategy, actor)
    approval = AnyaApproval(task_id=task.id, comment=payload.comment)
    database.add(approval)
    database.flush()
    _history(database, task_id=task.id, actor=actor, event_type="approval_created")
    record_audit(
        database,
        actor=actor,
        action=AuditAction.APPROVAL_CREATED,
        target_group_id=_group_id(database, task.strategy_id),
        details={"task_id": task.id, "approval_id": approval.id},
    )
    return approval


APPROVAL_TRANSITIONS = {
    ApprovalStatus.TO_SEND: {ApprovalStatus.SENT},
    ApprovalStatus.SENT: {ApprovalStatus.REVIEWING, ApprovalStatus.TO_SEND},
    ApprovalStatus.REVIEWING: {
        ApprovalStatus.REVISION,
        ApprovalStatus.APPROVED,
        ApprovalStatus.TO_SEND,
    },
    ApprovalStatus.REVISION: {ApprovalStatus.SENT, ApprovalStatus.TO_SEND},
    ApprovalStatus.APPROVED: {ApprovalStatus.TO_SEND},
}


def transition_approval(
    database: Session,
    actor: User,
    task: StrategyTask,
    approval: AnyaApproval,
    payload: ApprovalTransition,
    now: datetime,
) -> AnyaApproval:
    if payload.status not in APPROVAL_TRANSITIONS[approval.status]:
        raise _conflict("invalid_approval_transition", "Approval transition is not allowed")
    previous = approval.status
    values: dict[str, object] = {"status": payload.status}
    if payload.comment is not None:
        values["comment"] = payload.comment
    result = database.execute(
        update(AnyaApproval)
        .where(
            AnyaApproval.id == approval.id,
            AnyaApproval.version == payload.expected_version,
            _write_scope(task.strategy_id, actor),
        )
        .values(**values, version=AnyaApproval.version + 1, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        database.rollback()
        raise _conflict("version_conflict", "Approval changed by another request")
    database.refresh(approval)
    _history(
        database,
        task_id=task.id,
        actor=actor,
        event_type="approval_changed",
        details={"from": previous.value, "to": payload.status.value},
    )
    record_audit(
        database,
        actor=actor,
        action=AuditAction.APPROVAL_CHANGED,
        target_group_id=_group_id(database, task.strategy_id),
        details={"task_id": task.id, "from": previous.value, "to": payload.status.value},
    )
    return approval
