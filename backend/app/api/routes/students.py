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
from app.modules.auth.authorization import (
    require_group_read,
    require_group_update,
    require_student_read,
    require_student_update,
)
from app.modules.auth.dependencies import request_now
from app.modules.groups.models import Group
from app.modules.students.models import Student
from app.modules.students.schemas import (
    StudentCreate,
    StudentList,
    StudentRead,
    StudentSelfRead,
    StudentSummary,
    StudentUpdate,
    VersionRequest,
)
from app.modules.students.service import (
    archive_student,
    create_student,
    list_students,
    restore_student,
    update_student,
)
from app.modules.users.models import UserRole

router = APIRouter(tags=["students"])
ReadableGroup = Annotated[Group, Depends(require_group_read)]
WritableGroup = Annotated[Group, Depends(require_group_update)]
ReadableStudent = Annotated[Student, Depends(require_student_read)]
WritableStudent = Annotated[Student, Depends(require_student_update)]


@router.get("/api/v1/groups/{group_id}/students", response_model=StudentList)
def list_students_endpoint(
    group: ReadableGroup,
    database: Database,
    context: QueryContext,
    cursor: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> StudentList:
    students, next_cursor = list_students(
        database,
        context.user,
        group,
        cursor=cursor,
        limit=limit,
    )
    database.commit()
    return StudentList(
        items=[StudentSummary.model_validate(student) for student in students],
        next_cursor=next_cursor,
    )


@router.post(
    "/api/v1/groups/{group_id}/students",
    response_model=StudentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_student_endpoint(
    payload: StudentCreate,
    group: WritableGroup,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> Student:
    student = create_student(database, context.user, group, payload)
    commit(database)
    return student


@router.get("/api/v1/students/{student_id}", response_model=StudentRead | StudentSelfRead)
def get_student_endpoint(
    student: ReadableStudent,
    database: Database,
    context: QueryContext,
) -> StudentRead | StudentSelfRead:
    response = (
        StudentSelfRead.model_validate(student)
        if context.user.role is UserRole.STUDENT
        else StudentRead.model_validate(student)
    )
    database.commit()
    return response


@router.patch("/api/v1/students/{student_id}", response_model=StudentRead)
def update_student_endpoint(
    payload: StudentUpdate,
    request: Request,
    student: WritableStudent,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> Student:
    result = update_student(database, context.user, student, payload, request_now(request))
    commit(database)
    return result


@router.post("/api/v1/students/{student_id}/archive", response_model=StudentRead)
def archive_student_endpoint(
    payload: VersionRequest,
    request: Request,
    student: WritableStudent,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> Student:
    result = archive_student(
        database,
        context.user,
        student,
        payload.expected_version,
        request_now(request),
    )
    commit(database)
    return result


@router.post("/api/v1/students/{student_id}/restore", response_model=StudentRead)
def restore_student_endpoint(
    payload: VersionRequest,
    request: Request,
    student: WritableStudent,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> Student:
    result = restore_student(
        database,
        context.user,
        student,
        payload.expected_version,
        request_now(request),
    )
    commit(database)
    return result
