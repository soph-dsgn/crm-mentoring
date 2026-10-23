from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.db.session import get_db
from app.modules.auth.dependencies import (
    AuthContext,
    request_now,
    require_auth_context,
    require_csrf_session,
    require_same_origin,
)
from app.modules.auth.passwords import LoginFormatError, PasswordManager
from app.modules.users.schemas import (
    CuratorPublicResponse,
    GroupAssignmentResponse,
    LoginAccountRequest,
    OffboardCuratorRequest,
    OffboardResponse,
    PasswordResetResponse,
    ReassignCuratorRequest,
    SafeUserResponse,
    StudentAccountResponse,
    StudentTemporaryCredentialResponse,
    TemporaryCredentialResponse,
)
from app.modules.users.service import (
    assign_group,
    create_curator,
    create_student_account,
    deactivate_curator,
    deactivate_student_account,
    ensure_business_actor,
    get_curator,
    get_student_account,
    list_curators,
    offboard_curator,
    reset_password,
    transfer_owner,
)

router = APIRouter(prefix="/api/v1/admin", tags=["user-management"])


def _commit(database: Session) -> None:
    try:
        database.commit()
    except IntegrityError as error:
        _raise_integrity_conflict(database, error)


def _raise_integrity_conflict(database: Session, error: IntegrityError) -> None:
    database.rollback()
    message = str(error.orig).lower()
    if "last_active_owner_required" in message:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "last_owner_required",
            "At least one active owner must remain",
        ) from error
    if "normalized_login" in message or "users.login" in message:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "login_conflict",
            "Login is already in use",
        ) from error
    if "students.user_id" in message:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "student_account_exists",
            "Student already has an account",
        ) from error
    if "curator_has_groups" in message:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "curator_has_groups",
            "Reassign the curator's groups before deactivation",
        ) from error
    if "active_curator_required" in message:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_curator",
            "Curator must be an active admin",
        ) from error
    raise ApiError(
        status.HTTP_409_CONFLICT,
        "conflict",
        "Operation conflicts with current data",
    ) from error


def _mutating_context(
    context: Annotated[AuthContext, Depends(require_csrf_session)],
) -> AuthContext:
    ensure_business_actor(context.user)
    return context


def _business_context(
    context: Annotated[AuthContext, Depends(require_auth_context)],
) -> AuthContext:
    ensure_business_actor(context.user)
    return context


SameOrigin = Annotated[None, Depends(require_same_origin)]
MutationContext = Annotated[AuthContext, Depends(_mutating_context)]
QueryContext = Annotated[AuthContext, Depends(_business_context)]
Database = Annotated[Session, Depends(get_db)]


@router.post(
    "/curators",
    response_model=TemporaryCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_curator_endpoint(
    payload: LoginAccountRequest,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> TemporaryCredentialResponse:
    manager: PasswordManager = request.app.state.password_manager
    try:
        user, temporary_password = create_curator(database, manager, context.user, payload.login)
        _commit(database)
    except LoginFormatError as error:
        database.rollback()
        raise ApiError(422, "invalid_login", str(error)) from error
    except IntegrityError as error:
        _raise_integrity_conflict(database, error)
    return TemporaryCredentialResponse(user=user, temporary_password=temporary_password)


@router.get("/curators", response_model=list[CuratorPublicResponse])
def list_curators_endpoint(database: Database, context: QueryContext) -> list:
    result = list_curators(database, context.user)
    database.commit()
    return result


@router.get("/curators/{user_id}", response_model=SafeUserResponse)
def get_curator_endpoint(user_id: str, database: Database, context: QueryContext):
    result = get_curator(database, context.user, user_id)
    database.commit()
    return result


@router.post("/curators/{user_id}/deactivate", response_model=SafeUserResponse)
def deactivate_curator_endpoint(
    user_id: str,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    result = deactivate_curator(database, context.user, user_id, request_now(request))
    _commit(database)
    return result


@router.post(
    "/students/{student_id}/account",
    response_model=StudentTemporaryCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_student_account_endpoint(
    student_id: str,
    payload: LoginAccountRequest,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> StudentTemporaryCredentialResponse:
    manager: PasswordManager = request.app.state.password_manager
    try:
        student, user, temporary_password = create_student_account(
            database, manager, context.user, student_id, payload.login
        )
        _commit(database)
    except LoginFormatError as error:
        database.rollback()
        raise ApiError(422, "invalid_login", str(error)) from error
    except IntegrityError as error:
        _raise_integrity_conflict(database, error)
    return StudentTemporaryCredentialResponse(
        student_id=student.id,
        user=user,
        temporary_password=temporary_password,
    )


@router.get("/students/{student_id}/account", response_model=StudentAccountResponse)
def get_student_account_endpoint(student_id: str, database: Database, context: QueryContext):
    student, user = get_student_account(database, context.user, student_id)
    database.commit()
    return StudentAccountResponse(student_id=student.id, user=user)


@router.post("/students/{student_id}/deactivate-account", response_model=StudentAccountResponse)
def deactivate_student_account_endpoint(
    student_id: str,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> StudentAccountResponse:
    user = deactivate_student_account(database, context.user, student_id, request_now(request))
    _commit(database)
    return StudentAccountResponse(student_id=student_id, user=user)


@router.post("/users/{user_id}/reset-password", response_model=PasswordResetResponse)
def reset_password_endpoint(
    user_id: str,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> PasswordResetResponse:
    manager: PasswordManager = request.app.state.password_manager
    user, temporary_password = reset_password(
        database, manager, context.user, user_id, request_now(request)
    )
    _commit(database)
    return PasswordResetResponse(
        user_id=user.id,
        must_change_password=user.must_change_password,
        temporary_password=temporary_password,
    )


@router.post("/groups/{group_id}/reassign-curator", response_model=GroupAssignmentResponse)
def reassign_group_endpoint(
    group_id: str,
    payload: ReassignCuratorRequest,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> GroupAssignmentResponse:
    group = assign_group(database, context.user, group_id, payload.curator_id)
    _commit(database)
    return GroupAssignmentResponse(group_id=group.id, curator_id=group.curator_id)


@router.post("/curators/{user_id}/offboard", response_model=OffboardResponse)
def offboard_curator_endpoint(
    user_id: str,
    payload: OffboardCuratorRequest,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> OffboardResponse:
    try:
        user, group_ids = offboard_curator(
            database,
            context.user,
            user_id,
            payload.successor_curator_id,
            request_now(request),
        )
        _commit(database)
    except IntegrityError as error:
        _raise_integrity_conflict(database, error)
    return OffboardResponse(user=user, reassigned_group_ids=group_ids)


@router.post("/curators/{user_id}/transfer-ownership", response_model=SafeUserResponse)
def transfer_owner_endpoint(
    user_id: str,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
):
    try:
        successor = transfer_owner(database, context.user, user_id)
        _commit(database)
    except IntegrityError as error:
        _raise_integrity_conflict(database, error)
    return successor
