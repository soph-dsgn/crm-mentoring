from __future__ import annotations

from datetime import datetime

from fastapi import status
from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.api.errors import ApiError
from app.api.pagination import decode_cursor, encode_cursor
from app.modules.auth.dependencies import utc_now
from app.modules.groups.models import Group
from app.modules.homeworks.models import Homework, HomeworkHistory, HomeworkItem, HomeworkStatus
from app.modules.homeworks.schemas import HomeworkCreate, HomeworkTransition, HomeworkUpdate
from app.modules.strategies.models import (
    ReviewStatus,
    Strategy,
    StrategyTask,
    StudyStatus,
    TaskHistory,
)
from app.modules.strategies.service import get_strategy
from app.modules.students.models import Student
from app.modules.users.audit import AuditAction
from app.modules.users.models import User, UserRole
from app.modules.users.service import record_audit


def _not_found(resource: str) -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, "not_found", f"{resource} not found")


def _forbidden() -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, "forbidden", "Operation not permitted")


def _conflict(code: str, message: str) -> ApiError:
    return ApiError(status.HTTP_409_CONFLICT, code, message)


def _admin_scope(strategy_id: str, actor: User):
    statement = (
        select(Strategy.id)
        .join(Student, Strategy.student_id == Student.id)
        .join(Group, Student.group_id == Group.id)
        .where(Strategy.id == strategy_id)
    )
    if not actor.is_owner:
        statement = statement.where(Group.curator_id == actor.id)
    return exists(statement)


def _student_scope(strategy_id: str, actor: User):
    return exists(
        select(Strategy.id)
        .join(Student, Strategy.student_id == Student.id)
        .where(Strategy.id == strategy_id, Student.user_id == actor.id)
    )


def _group_id(database: Session, strategy_id: str) -> str:
    group_id = database.scalar(
        select(Student.group_id)
        .join(Strategy, Strategy.student_id == Student.id)
        .where(Strategy.id == strategy_id)
    )
    if group_id is None:
        raise _not_found("Strategy")
    return group_id


def _load_homework(database: Session, homework_id: str) -> Homework | None:
    return database.scalar(
        select(Homework)
        .options(selectinload(Homework.items).selectinload(HomeworkItem.task))
        .where(Homework.id == homework_id)
    )


def get_homework(database: Session, actor: User, homework_id: str, *, write: bool) -> Homework:
    homework = _load_homework(database, homework_id)
    if homework is None:
        raise _not_found("Homework")
    get_strategy(database, actor, homework.strategy_id, write=write)
    return homework


def list_homeworks(
    database: Session,
    strategy: Strategy,
    *,
    cursor: str | None,
    limit: int,
    include_archived: bool,
) -> tuple[list[Homework], str | None]:
    statement = (
        select(Homework)
        .options(selectinload(Homework.items).selectinload(HomeworkItem.task))
        .where(Homework.strategy_id == strategy.id)
    )
    if not include_archived:
        statement = statement.where(Homework.archived_at.is_(None))
    cursor_id = decode_cursor(cursor)
    if cursor_id is not None:
        row = database.get(Homework, cursor_id)
        if row is None or row.strategy_id != strategy.id:
            raise ApiError(422, "invalid_cursor", "Pagination cursor is invalid")
        statement = statement.where(
            or_(
                Homework.created_at < row.created_at,
                and_(Homework.created_at == row.created_at, Homework.id > row.id),
            )
        )
    rows = list(
        database.scalars(
            statement.order_by(Homework.created_at.desc(), Homework.id).limit(limit + 1)
        )
    )
    items = rows[:limit]
    return items, encode_cursor(items[-1].id) if len(rows) > limit else None


def create_homework(
    database: Session,
    actor: User,
    strategy: Strategy,
    payload: HomeworkCreate,
) -> Homework:
    if len(set(payload.task_ids)) != len(payload.task_ids):
        raise ApiError(422, "invalid_task_selection", "Tasks must be unique")
    lock = database.execute(
        update(Strategy)
        .where(Strategy.id == strategy.id, _admin_scope(strategy.id, actor))
        .values(version=Strategy.version)
        .execution_options(synchronize_session=False)
    )
    if lock.rowcount != 1:
        database.rollback()
        raise _conflict("curator_assignment_changed", "Curator assignment changed")
    tasks = list(
        database.scalars(
            select(StrategyTask).where(
                StrategyTask.id.in_(payload.task_ids),
                StrategyTask.strategy_id == strategy.id,
                StrategyTask.archived_at.is_(None),
            )
        )
    )
    tasks_by_id = {task.id: task for task in tasks}
    if set(tasks_by_id) != set(payload.task_ids):
        raise ApiError(
            422,
            "invalid_task_selection",
            "Every task must be active and belong to the strategy",
        )
    homework = Homework(
        strategy_id=strategy.id,
        title=payload.title,
        description=payload.description,
        links={key: str(value) for key, value in payload.links.items()},
        due_at=payload.due_at,
    )
    database.add(homework)
    database.flush()
    for position, task_id in enumerate(payload.task_ids):
        task = tasks_by_id[task_id]
        database.add(
            HomeworkItem(
                homework_id=homework.id,
                strategy_id=strategy.id,
                task_id=task.id,
                position=position,
                title=task.title,
                description=task.description,
                materials=list(task.materials),
                links=dict(task.links),
                period_text=task.period_text,
                due_at=task.due_at,
            )
        )
    _history(database, homework, actor, "homework_created")
    record_audit(
        database,
        actor=actor,
        action=AuditAction.HOMEWORK_CREATED,
        target_group_id=_group_id(database, strategy.id),
        details={"homework_id": homework.id, "strategy_id": strategy.id},
    )
    database.flush()
    return _load_homework(database, homework.id)


def update_homework(
    database: Session,
    actor: User,
    homework: Homework,
    payload: HomeworkUpdate,
    now: datetime,
) -> Homework:
    if homework.status is not HomeworkStatus.DRAFT:
        raise _conflict("homework_immutable", "Issued homework content cannot be changed")
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if "links" in values:
        values["links"] = {key: str(value) for key, value in payload.links.items()}
    result = database.execute(
        update(Homework)
        .where(
            Homework.id == homework.id,
            Homework.version == payload.expected_version,
            _admin_scope(homework.strategy_id, actor),
        )
        .values(**values, version=Homework.version + 1, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        database.rollback()
        raise _conflict("version_conflict", "Homework changed by another request")
    database.refresh(homework)
    record_audit(
        database,
        actor=actor,
        action=AuditAction.HOMEWORK_UPDATED,
        target_group_id=_group_id(database, homework.strategy_id),
        details={"homework_id": homework.id, "fields": sorted(values)},
    )
    return _load_homework(database, homework.id)


TRANSITIONS = {
    HomeworkStatus.DRAFT: {HomeworkStatus.ISSUED},
    HomeworkStatus.ISSUED: {HomeworkStatus.PROGRESS, HomeworkStatus.SUBMITTED},
    HomeworkStatus.PROGRESS: {HomeworkStatus.SUBMITTED},
    HomeworkStatus.SUBMITTED: {HomeworkStatus.REVISION, HomeworkStatus.ACCEPTED},
    HomeworkStatus.REVISION: {HomeworkStatus.PROGRESS, HomeworkStatus.SUBMITTED},
    HomeworkStatus.ACCEPTED: set(),
}


def _history(
    database: Session,
    homework: Homework,
    actor: User,
    event_type: str,
    *,
    previous: HomeworkStatus | None = None,
    current: HomeworkStatus | None = None,
    created_at: datetime | None = None,
) -> None:
    database.add(
        HomeworkHistory(
            homework_id=homework.id,
            actor_user_id=actor.id,
            event_type=event_type,
            from_status=previous,
            to_status=current,
            details={},
            created_at=created_at or utc_now(),
        )
    )


def _update_tasks_for_review(
    database: Session,
    homework: Homework,
    actor: User,
    target: HomeworkStatus,
    now: datetime,
) -> None:
    if target not in {HomeworkStatus.SUBMITTED, HomeworkStatus.REVISION, HomeworkStatus.ACCEPTED}:
        return
    review_status = {
        HomeworkStatus.SUBMITTED: ReviewStatus.PENDING,
        HomeworkStatus.REVISION: ReviewStatus.REVISION,
        HomeworkStatus.ACCEPTED: ReviewStatus.ACCEPTED,
    }[target]
    study_status = (
        StudyStatus.DONE if target is HomeworkStatus.ACCEPTED else StudyStatus.IN_PROGRESS
    )
    event_type = {
        HomeworkStatus.SUBMITTED: "homework_submitted",
        HomeworkStatus.REVISION: "homework_revision_requested",
        HomeworkStatus.ACCEPTED: "homework_accepted",
    }[target]
    for item in sorted(homework.items, key=lambda item: item.task_id):
        task = item.task
        revision_history = exists(
            select(HomeworkHistory.id).where(
                HomeworkHistory.homework_id == HomeworkItem.homework_id,
                HomeworkHistory.to_status == HomeworkStatus.REVISION,
            )
        )
        competing_review = database.scalar(
            select(
                exists(
                    select(HomeworkItem.id)
                    .join(Homework, HomeworkItem.homework_id == Homework.id)
                    .where(
                        HomeworkItem.task_id == task.id,
                        HomeworkItem.homework_id != homework.id,
                        Homework.archived_at.is_(None),
                        or_(
                            Homework.status.in_(
                                [HomeworkStatus.SUBMITTED, HomeworkStatus.REVISION]
                            ),
                            and_(
                                Homework.status == HomeworkStatus.PROGRESS,
                                revision_history,
                            ),
                        ),
                    )
                )
            )
        )
        if competing_review:
            database.rollback()
            raise _conflict(
                "task_review_conflict",
                "A task is already under review in another homework",
            )
        result = database.execute(
            update(StrategyTask)
            .where(
                StrategyTask.id == task.id,
                StrategyTask.strategy_id == homework.strategy_id,
                StrategyTask.version == task.version,
            )
            .values(
                review_status=review_status,
                study_status=study_status,
                version=StrategyTask.version + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            database.rollback()
            raise _conflict("version_conflict", "Strategy task changed by another request")
        database.add(
            TaskHistory(
                task_id=task.id,
                actor_user_id=actor.id,
                event_type=event_type,
                details={"homework_id": homework.id},
                created_at=now,
            )
        )


def transition_homework(
    database: Session,
    actor: User,
    homework: Homework,
    payload: HomeworkTransition,
    now: datetime,
) -> Homework:
    if homework.archived_at is not None:
        raise _conflict("homework_archived", "Restore the homework before changing it")
    if payload.status not in TRANSITIONS[homework.status]:
        raise _conflict("invalid_homework_transition", "Homework transition is not allowed")
    is_student = actor.role is UserRole.STUDENT
    if is_student and payload.status not in {HomeworkStatus.PROGRESS, HomeworkStatus.SUBMITTED}:
        raise _forbidden()
    if is_student and payload.curator_feedback is not None:
        raise _forbidden()
    if not is_student and actor.role is not UserRole.ADMIN:
        raise _forbidden()
    if not is_student:
        get_strategy(database, actor, homework.strategy_id, write=True)
    if payload.status is HomeworkStatus.SUBMITTED:
        submission_text = payload.submission_text or homework.submission_text
        submission_links = payload.submission_links or homework.submission_links
        if not submission_text.strip() and not submission_links:
            raise ApiError(422, "submission_required", "Submission text or link is required")
    scope = (
        _student_scope(homework.strategy_id, actor)
        if is_student
        else _admin_scope(homework.strategy_id, actor)
    )
    values: dict[str, object] = {"status": payload.status, "updated_at": now}
    if payload.submission_text is not None:
        values["submission_text"] = payload.submission_text
    if payload.submission_links is not None:
        values["submission_links"] = {
            key: str(value) for key, value in payload.submission_links.items()
        }
    if payload.curator_feedback is not None:
        values["curator_feedback"] = payload.curator_feedback
    if payload.status is HomeworkStatus.ISSUED:
        values["issued_at"] = now
    if payload.status is HomeworkStatus.SUBMITTED:
        values["submitted_at"] = now
        values["reviewed_at"] = None
    if payload.status in {HomeworkStatus.REVISION, HomeworkStatus.ACCEPTED}:
        values["reviewed_at"] = now
    previous = homework.status
    result = database.execute(
        update(Homework)
        .where(
            Homework.id == homework.id,
            Homework.version == payload.expected_version,
            scope,
        )
        .values(**values, version=Homework.version + 1)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        database.rollback()
        raise _conflict("version_conflict", "Homework changed by another request")
    _update_tasks_for_review(database, homework, actor, payload.status, now)
    _history(
        database,
        homework,
        actor,
        "homework_status_changed",
        previous=previous,
        current=payload.status,
        created_at=now,
    )
    record_audit(
        database,
        actor=actor,
        action=AuditAction.HOMEWORK_TRANSITIONED,
        target_group_id=_group_id(database, homework.strategy_id),
        details={
            "homework_id": homework.id,
            "from": previous.value,
            "to": payload.status.value,
        },
    )
    database.flush()
    database.expire_all()
    return _load_homework(database, homework.id)


def set_homework_archived(
    database: Session,
    actor: User,
    homework: Homework,
    expected_version: int,
    now: datetime,
    *,
    archived: bool,
) -> Homework:
    if archived == (homework.archived_at is not None):
        raise _conflict(
            "invalid_homework_transition",
            "Homework is already archived" if archived else "Homework is not archived",
        )
    if archived and any(
        item.task.review_status in {ReviewStatus.PENDING, ReviewStatus.REVISION}
        for item in homework.items
    ):
        raise _conflict(
            "homework_review_active",
            "Complete the homework review before archiving it",
        )
    result = database.execute(
        update(Homework)
        .where(
            Homework.id == homework.id,
            Homework.version == expected_version,
            _admin_scope(homework.strategy_id, actor),
        )
        .values(
            archived_at=now if archived else None,
            version=Homework.version + 1,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        database.rollback()
        raise _conflict("version_conflict", "Homework changed by another request")
    database.refresh(homework)
    _history(
        database,
        homework,
        actor,
        "homework_archived" if archived else "homework_restored",
        created_at=now,
    )
    record_audit(
        database,
        actor=actor,
        action=AuditAction.HOMEWORK_ARCHIVED if archived else AuditAction.HOMEWORK_RESTORED,
        target_group_id=_group_id(database, homework.strategy_id),
        details={"homework_id": homework.id},
    )
    database.flush()
    return _load_homework(database, homework.id)


def list_history(
    database: Session,
    homework: Homework,
    *,
    cursor: str | None,
    limit: int,
) -> tuple[list[HomeworkHistory], str | None]:
    statement = select(HomeworkHistory).where(HomeworkHistory.homework_id == homework.id)
    cursor_id = decode_cursor(cursor)
    if cursor_id is not None:
        row = database.get(HomeworkHistory, cursor_id)
        if row is None or row.homework_id != homework.id:
            raise ApiError(422, "invalid_cursor", "Pagination cursor is invalid")
        statement = statement.where(
            or_(
                HomeworkHistory.created_at > row.created_at,
                and_(
                    HomeworkHistory.created_at == row.created_at,
                    HomeworkHistory.id > row.id,
                ),
            )
        )
    rows = list(
        database.scalars(
            statement.order_by(HomeworkHistory.created_at, HomeworkHistory.id).limit(limit + 1)
        )
    )
    items = rows[:limit]
    return items, encode_cursor(items[-1].id) if len(rows) > limit else None
