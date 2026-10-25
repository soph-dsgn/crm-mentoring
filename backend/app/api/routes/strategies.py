from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from sqlalchemy.exc import IntegrityError

from app.api.routes._shared import (
    Database,
    MutationContext,
    QueryContext,
    SameOrigin,
    commit,
    raise_integrity_conflict,
)
from app.modules.auth.dependencies import request_now
from app.modules.strategies.schemas import (
    ApprovalCreate,
    ApprovalRead,
    ApprovalTransition,
    HistoryList,
    HistoryRead,
    HistorySelfList,
    HistorySelfRead,
    SectionCreate,
    SectionRead,
    SectionReorder,
    SectionUpdate,
    StrategyCreate,
    StrategyRead,
    TaskCreate,
    TaskRead,
    TaskStatusChange,
    TaskUpdate,
    VersionRequest,
)
from app.modules.strategies.service import (
    change_task_status,
    create_approval,
    create_section,
    create_strategy,
    create_task,
    get_approval,
    get_section,
    get_strategy,
    get_strategy_for_student,
    get_student_for_strategy,
    get_task,
    list_history,
    list_sections,
    list_tasks,
    reorder_sections,
    reorder_tasks,
    set_task_archived,
    transition_approval,
    update_section,
    update_task,
)
from app.modules.users.models import UserRole

router = APIRouter(prefix="/api/v1", tags=["strategies"])


@router.get("/students/{student_id}/strategy", response_model=StrategyRead)
def get_strategy_endpoint(
    student_id: str,
    database: Database,
    context: QueryContext,
):
    get_student_for_strategy(database, context.user, student_id, write=False)
    strategy = get_strategy_for_student(database, student_id)
    database.commit()
    return strategy


@router.post(
    "/students/{student_id}/strategy",
    response_model=StrategyRead,
    status_code=status.HTTP_201_CREATED,
)
def create_strategy_endpoint(
    student_id: str,
    payload: StrategyCreate,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    student = get_student_for_strategy(database, context.user, student_id, write=True)
    try:
        strategy = create_strategy(database, context.user, student, payload)
    except IntegrityError as error:
        raise_integrity_conflict(database, error)
    commit(database)
    return strategy


@router.get("/strategies/{strategy_id}/sections", response_model=list[SectionRead])
def list_sections_endpoint(
    strategy_id: str,
    database: Database,
    context: QueryContext,
):
    strategy = get_strategy(database, context.user, strategy_id, write=False)
    sections = list_sections(database, strategy)
    database.commit()
    return sections


@router.post(
    "/strategies/{strategy_id}/sections",
    response_model=SectionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_section_endpoint(
    strategy_id: str,
    payload: SectionCreate,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    strategy = get_strategy(database, context.user, strategy_id, write=True)
    try:
        section = create_section(database, context.user, strategy, payload)
    except IntegrityError as error:
        raise_integrity_conflict(database, error)
    commit(database)
    return section


@router.patch("/strategy-sections/{section_id}", response_model=SectionRead)
def update_section_endpoint(
    section_id: str,
    payload: SectionUpdate,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    section = get_section(database, context.user, section_id, write=True)
    result = update_section(database, context.user, section, payload, request_now(request))
    commit(database)
    return result


@router.post("/strategies/{strategy_id}/sections/reorder", response_model=list[SectionRead])
def reorder_sections_endpoint(
    strategy_id: str,
    payload: SectionReorder,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    strategy = get_strategy(database, context.user, strategy_id, write=True)
    sections = reorder_sections(database, context.user, strategy, payload, request_now(request))
    commit(database)
    return sections


@router.post(
    "/strategy-sections/{section_id}/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
)
def create_task_endpoint(
    section_id: str,
    payload: TaskCreate,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    section = get_section(database, context.user, section_id, write=True)
    try:
        task = create_task(database, context.user, section, payload)
    except IntegrityError as error:
        raise_integrity_conflict(database, error)
    commit(database)
    return task


@router.get("/strategy-sections/{section_id}/tasks", response_model=list[TaskRead])
def list_tasks_endpoint(
    section_id: str,
    database: Database,
    context: QueryContext,
    include_archived: bool = False,
):
    section = get_section(database, context.user, section_id, write=False)
    tasks = list_tasks(database, section, include_archived=include_archived)
    database.commit()
    return tasks


@router.post("/strategy-sections/{section_id}/tasks/reorder", response_model=list[TaskRead])
def reorder_tasks_endpoint(
    section_id: str,
    payload: SectionReorder,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    section = get_section(database, context.user, section_id, write=True)
    tasks = reorder_tasks(database, context.user, section, payload, request_now(request))
    commit(database)
    return tasks


@router.get("/strategy-tasks/{task_id}", response_model=TaskRead)
def get_task_endpoint(
    task_id: str,
    database: Database,
    context: QueryContext,
):
    task = get_task(database, context.user, task_id, write=False)
    database.commit()
    return task


@router.patch("/strategy-tasks/{task_id}", response_model=TaskRead)
def update_task_endpoint(
    task_id: str,
    payload: TaskUpdate,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    task = get_task(database, context.user, task_id, write=True)
    result = update_task(database, context.user, task, payload, request_now(request))
    commit(database)
    return result


@router.post("/strategy-tasks/{task_id}/study-status", response_model=TaskRead)
def change_task_status_endpoint(
    task_id: str,
    payload: TaskStatusChange,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    task = get_task(database, context.user, task_id, write=True)
    result = change_task_status(database, context.user, task, payload, request_now(request))
    commit(database)
    return result


def _archive_task(
    task_id: str,
    payload: VersionRequest,
    request: Request,
    database: Database,
    context: MutationContext,
    *,
    archived: bool,
):
    task = get_task(database, context.user, task_id, write=True)
    result = set_task_archived(
        database,
        context.user,
        task,
        payload.expected_version,
        request_now(request),
        archived=archived,
    )
    commit(database)
    return result


@router.post("/strategy-tasks/{task_id}/archive", response_model=TaskRead)
def archive_task_endpoint(
    task_id: str,
    payload: VersionRequest,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    return _archive_task(task_id, payload, request, database, context, archived=True)


@router.post("/strategy-tasks/{task_id}/restore", response_model=TaskRead)
def restore_task_endpoint(
    task_id: str,
    payload: VersionRequest,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    return _archive_task(task_id, payload, request, database, context, archived=False)


@router.get(
    "/strategy-tasks/{task_id}/history",
    response_model=HistoryList | HistorySelfList,
)
def list_task_history_endpoint(
    task_id: str,
    database: Database,
    context: QueryContext,
    cursor: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    task = get_task(database, context.user, task_id, write=False)
    items, next_cursor = list_history(database, task, cursor=cursor, limit=limit)
    database.commit()
    if context.user.role is UserRole.STUDENT:
        return HistorySelfList(
            items=[HistorySelfRead.model_validate(item) for item in items],
            next_cursor=next_cursor,
        )
    return HistoryList(
        items=[HistoryRead.model_validate(item) for item in items], next_cursor=next_cursor
    )


@router.get("/strategy-tasks/{task_id}/approval", response_model=ApprovalRead)
def get_approval_endpoint(
    task_id: str,
    database: Database,
    context: QueryContext,
):
    task = get_task(database, context.user, task_id, write=False)
    approval = get_approval(database, task)
    database.commit()
    return approval


@router.post(
    "/strategy-tasks/{task_id}/approval",
    response_model=ApprovalRead,
    status_code=status.HTTP_201_CREATED,
)
def create_approval_endpoint(
    task_id: str,
    payload: ApprovalCreate,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    task = get_task(database, context.user, task_id, write=True)
    try:
        approval = create_approval(database, context.user, task, payload)
    except IntegrityError as error:
        raise_integrity_conflict(database, error)
    commit(database)
    return approval


@router.post("/strategy-tasks/{task_id}/approval/transition", response_model=ApprovalRead)
def transition_approval_endpoint(
    task_id: str,
    payload: ApprovalTransition,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    task = get_task(database, context.user, task_id, write=True)
    approval = get_approval(database, task)
    result = transition_approval(
        database, context.user, task, approval, payload, request_now(request)
    )
    commit(database)
    return result
