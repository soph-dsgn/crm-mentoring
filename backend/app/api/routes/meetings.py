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
from app.modules.meetings.schemas import (
    MeetingCreate,
    MeetingList,
    MeetingRead,
    MeetingSelfList,
    MeetingSelfRead,
    MeetingUpdate,
)
from app.modules.meetings.service import (
    create_meeting,
    get_meeting,
    get_student,
    list_meetings,
    set_meeting_archived,
    update_meeting,
)
from app.modules.strategies.schemas import VersionRequest
from app.modules.users.models import UserRole

router = APIRouter(prefix="/api/v1", tags=["meetings"])


@router.get(
    "/students/{student_id}/meetings",
    response_model=MeetingList | MeetingSelfList,
)
def list_meetings_endpoint(
    student_id: str,
    database: Database,
    context: QueryContext,
    cursor: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    include_archived: bool = False,
):
    student = get_student(database, context.user, student_id, write=False)
    items, next_cursor = list_meetings(
        database,
        student,
        cursor=cursor,
        limit=limit,
        include_archived=include_archived,
    )
    database.commit()
    if context.user.role is UserRole.STUDENT:
        return MeetingSelfList(
            items=[MeetingSelfRead.model_validate(item) for item in items],
            next_cursor=next_cursor,
        )
    return MeetingList(
        items=[MeetingRead.model_validate(item) for item in items], next_cursor=next_cursor
    )


@router.post(
    "/students/{student_id}/meetings",
    response_model=MeetingRead,
    status_code=status.HTTP_201_CREATED,
)
def create_meeting_endpoint(
    student_id: str,
    payload: MeetingCreate,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    student = get_student(database, context.user, student_id, write=True)
    try:
        meeting = create_meeting(database, context.user, student, payload)
    except IntegrityError as error:
        raise_integrity_conflict(database, error)
    commit(database)
    return meeting


@router.get("/meetings/{meeting_id}", response_model=MeetingRead | MeetingSelfRead)
def get_meeting_endpoint(meeting_id: str, database: Database, context: QueryContext):
    meeting = get_meeting(database, context.user, meeting_id, write=False)
    database.commit()
    if context.user.role is UserRole.STUDENT:
        return MeetingSelfRead.model_validate(meeting)
    return MeetingRead.model_validate(meeting)


@router.patch("/meetings/{meeting_id}", response_model=MeetingRead)
def update_meeting_endpoint(
    meeting_id: str,
    payload: MeetingUpdate,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    meeting = get_meeting(database, context.user, meeting_id, write=True)
    result = update_meeting(database, context.user, meeting, payload, request_now(request))
    commit(database)
    return result


def _archive_meeting(
    meeting_id: str,
    payload: VersionRequest,
    request: Request,
    database: Database,
    context: MutationContext,
    *,
    archived: bool,
):
    meeting = get_meeting(database, context.user, meeting_id, write=True)
    result = set_meeting_archived(
        database,
        context.user,
        meeting,
        payload.expected_version,
        request_now(request),
        archived=archived,
    )
    commit(database)
    return result


@router.post("/meetings/{meeting_id}/archive", response_model=MeetingRead)
def archive_meeting_endpoint(
    meeting_id: str,
    payload: VersionRequest,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    return _archive_meeting(meeting_id, payload, request, database, context, archived=True)


@router.post("/meetings/{meeting_id}/restore", response_model=MeetingRead)
def restore_meeting_endpoint(
    meeting_id: str,
    payload: VersionRequest,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    return _archive_meeting(meeting_id, payload, request, database, context, archived=False)
