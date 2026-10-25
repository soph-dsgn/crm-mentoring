from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.routes._shared import (
    Database,
    MutationContext,
    QueryContext,
    SameOrigin,
    commit,
)
from app.modules.auth.authorization import require_group_read, require_group_update
from app.modules.auth.dependencies import request_now
from app.modules.groups.models import Group, GroupStatus
from app.modules.groups.schemas import (
    GroupCreate,
    GroupList,
    GroupRead,
    GroupStudentList,
    GroupStudentRead,
    GroupStudentSummary,
    GroupSummary,
    GroupUpdate,
    VersionRequest,
)
from app.modules.groups.service import (
    archive_group,
    create_group,
    list_groups,
    restore_group,
    update_group,
)
from app.modules.users.models import UserRole

router = APIRouter(prefix="/api/v1/groups", tags=["groups"])
ReadableGroup = Annotated[Group, Depends(require_group_read)]
WritableGroup = Annotated[Group, Depends(require_group_update)]


@router.get("", response_model=GroupList | GroupStudentList)
def list_groups_endpoint(
    database: Database,
    context: QueryContext,
    lifecycle: GroupStatus | None = None,
    curator_id: Annotated[str | None, Query(max_length=36)] = None,
    cursor: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> GroupList | GroupStudentList:
    groups, next_cursor = list_groups(
        database,
        context.user,
        lifecycle=lifecycle,
        curator_id=curator_id,
        cursor=cursor,
        limit=limit,
    )
    database.commit()
    if context.user.role is UserRole.STUDENT:
        return GroupStudentList(
            items=[GroupStudentSummary.model_validate(group) for group in groups],
            next_cursor=next_cursor,
        )
    return GroupList(
        items=[GroupSummary.model_validate(group) for group in groups], next_cursor=next_cursor
    )


@router.post("", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def create_group_endpoint(
    payload: GroupCreate,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> Group:
    group = create_group(database, context.user, payload)
    commit(database)
    return group


@router.get("/{group_id}", response_model=GroupRead | GroupStudentRead)
def get_group_endpoint(
    group: ReadableGroup,
    database: Database,
    context: QueryContext,
) -> GroupRead | GroupStudentRead:
    response = (
        GroupStudentRead.model_validate(group)
        if context.user.role is UserRole.STUDENT
        else GroupRead.model_validate(group)
    )
    database.commit()
    return response


@router.patch("/{group_id}", response_model=GroupRead)
def update_group_endpoint(
    payload: GroupUpdate,
    request: Request,
    group: WritableGroup,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> Group:
    result = update_group(database, context.user, group, payload, request_now(request))
    commit(database)
    return result


@router.post("/{group_id}/archive", response_model=GroupRead)
def archive_group_endpoint(
    payload: VersionRequest,
    request: Request,
    group: WritableGroup,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> Group:
    result = archive_group(
        database,
        context.user,
        group,
        payload.expected_version,
        request_now(request),
    )
    commit(database)
    return result


@router.post("/{group_id}/restore", response_model=GroupRead)
def restore_group_endpoint(
    payload: VersionRequest,
    request: Request,
    group: WritableGroup,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> Group:
    result = restore_group(
        database,
        context.user,
        group,
        payload.expected_version,
        request_now(request),
    )
    commit(database)
    return result
