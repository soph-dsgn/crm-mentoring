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
from app.modules.homeworks.schemas import (
    HomeworkCreate,
    HomeworkHistoryList,
    HomeworkHistoryRead,
    HomeworkHistorySelfList,
    HomeworkHistorySelfRead,
    HomeworkList,
    HomeworkRead,
    HomeworkTransition,
    HomeworkUpdate,
)
from app.modules.homeworks.service import (
    create_homework,
    get_homework,
    list_history,
    list_homeworks,
    set_homework_archived,
    transition_homework,
    update_homework,
)
from app.modules.strategies.schemas import VersionRequest
from app.modules.strategies.service import get_strategy
from app.modules.users.models import UserRole

router = APIRouter(prefix="/api/v1", tags=["homeworks"])


@router.get("/strategies/{strategy_id}/homeworks", response_model=HomeworkList)
def list_homeworks_endpoint(
    strategy_id: str,
    database: Database,
    context: QueryContext,
    cursor: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    include_archived: bool = False,
):
    strategy = get_strategy(database, context.user, strategy_id, write=False)
    items, next_cursor = list_homeworks(
        database,
        strategy,
        cursor=cursor,
        limit=limit,
        include_archived=include_archived,
    )
    database.commit()
    return HomeworkList(
        items=[HomeworkRead.model_validate(item) for item in items], next_cursor=next_cursor
    )


@router.post(
    "/strategies/{strategy_id}/homeworks",
    response_model=HomeworkRead,
    status_code=status.HTTP_201_CREATED,
)
def create_homework_endpoint(
    strategy_id: str,
    payload: HomeworkCreate,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    strategy = get_strategy(database, context.user, strategy_id, write=True)
    try:
        homework = create_homework(database, context.user, strategy, payload)
    except IntegrityError as error:
        raise_integrity_conflict(database, error)
    commit(database)
    return homework


@router.get("/homeworks/{homework_id}", response_model=HomeworkRead)
def get_homework_endpoint(homework_id: str, database: Database, context: QueryContext):
    homework = get_homework(database, context.user, homework_id, write=False)
    database.commit()
    return homework


@router.patch("/homeworks/{homework_id}", response_model=HomeworkRead)
def update_homework_endpoint(
    homework_id: str,
    payload: HomeworkUpdate,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    homework = get_homework(database, context.user, homework_id, write=True)
    result = update_homework(database, context.user, homework, payload, request_now(request))
    commit(database)
    return result


@router.post("/homeworks/{homework_id}/transitions", response_model=HomeworkRead)
def transition_homework_endpoint(
    homework_id: str,
    payload: HomeworkTransition,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    homework = get_homework(database, context.user, homework_id, write=False)
    result = transition_homework(database, context.user, homework, payload, request_now(request))
    commit(database)
    return result


def _archive_homework(
    homework_id: str,
    payload: VersionRequest,
    request: Request,
    database: Database,
    context: MutationContext,
    *,
    archived: bool,
):
    homework = get_homework(database, context.user, homework_id, write=True)
    result = set_homework_archived(
        database,
        context.user,
        homework,
        payload.expected_version,
        request_now(request),
        archived=archived,
    )
    commit(database)
    return result


@router.post("/homeworks/{homework_id}/archive", response_model=HomeworkRead)
def archive_homework_endpoint(
    homework_id: str,
    payload: VersionRequest,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    return _archive_homework(homework_id, payload, request, database, context, archived=True)


@router.post("/homeworks/{homework_id}/restore", response_model=HomeworkRead)
def restore_homework_endpoint(
    homework_id: str,
    payload: VersionRequest,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    return _archive_homework(homework_id, payload, request, database, context, archived=False)


@router.get(
    "/homeworks/{homework_id}/history",
    response_model=HomeworkHistoryList | HomeworkHistorySelfList,
)
def list_homework_history_endpoint(
    homework_id: str,
    database: Database,
    context: QueryContext,
    cursor: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    homework = get_homework(database, context.user, homework_id, write=False)
    items, next_cursor = list_history(database, homework, cursor=cursor, limit=limit)
    database.commit()
    if context.user.role is UserRole.STUDENT:
        return HomeworkHistorySelfList(
            items=[HomeworkHistorySelfRead.model_validate(item) for item in items],
            next_cursor=next_cursor,
        )
    return HomeworkHistoryList(
        items=[HomeworkHistoryRead.model_validate(item) for item in items],
        next_cursor=next_cursor,
    )
