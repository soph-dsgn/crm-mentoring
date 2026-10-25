from __future__ import annotations

from typing import Annotated

from fastapi import Depends, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.db.session import get_db
from app.modules.auth.dependencies import (
    AuthContext,
    require_auth_context,
    require_csrf_session,
    require_same_origin,
)
from app.modules.users.service import ensure_business_actor


def commit(database: Session) -> None:
    try:
        database.commit()
    except IntegrityError as error:
        raise_integrity_conflict(database, error)


def raise_integrity_conflict(database: Session, error: IntegrityError) -> None:
    database.rollback()
    message = str(error.orig).lower()
    mappings = (
        (
            "last_active_owner_required",
            "last_owner_required",
            "At least one active owner must remain",
            409,
        ),
        ("normalized_login", "login_conflict", "Login is already in use", 409),
        ("users.login", "login_conflict", "Login is already in use", 409),
        ("students.user_id", "student_account_exists", "Student already has an account", 409),
        (
            "curator_has_groups",
            "curator_has_groups",
            "Reassign the curator's groups before deactivation",
            409,
        ),
        ("active_curator_required", "invalid_curator", "Curator must be an active admin", 422),
        ("group_archived", "group_archived", "Cannot create a student in an archived group", 409),
        ("strategies.student_id", "strategy_exists", "Student already has a strategy", 409),
        (
            "strategy_sections.strategy_id, strategy_sections.position",
            "position_conflict",
            "Section position is already in use",
            409,
        ),
        (
            "strategy_tasks.section_id, strategy_tasks.position",
            "position_conflict",
            "Task position is already in use",
            409,
        ),
    )
    for marker, code, public_message, status_code in mappings:
        if marker in message:
            raise ApiError(status_code, code, public_message) from error
    raise ApiError(
        status.HTTP_409_CONFLICT,
        "conflict",
        "Operation conflicts with current data",
    ) from error


def mutating_context(
    context: Annotated[AuthContext, Depends(require_csrf_session)],
) -> AuthContext:
    ensure_business_actor(context.user)
    return context


def business_context(
    context: Annotated[AuthContext, Depends(require_auth_context)],
) -> AuthContext:
    ensure_business_actor(context.user)
    return context


MutationContext = Annotated[AuthContext, Depends(mutating_context)]
QueryContext = Annotated[AuthContext, Depends(business_context)]
Database = Annotated[Session, Depends(get_db)]
SameOrigin = Annotated[None, Depends(require_same_origin)]
