from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.core.config import Settings
from app.db import models as domain_models  # noqa: F401
from app.db.session import get_db
from app.modules.auth.dependencies import (
    AuthContext,
    hash_secret,
    request_now,
    require_auth_context,
    require_csrf_session,
    require_same_origin,
    resolve_auth_context,
)
from app.modules.auth.models import AuthSession, LoginAttempt
from app.modules.auth.passwords import (
    LoginFormatError,
    PasswordManager,
    canonicalize_login,
    normalize_login,
)
from app.modules.auth.schemas import ChangePasswordRequest, CurrentUserResponse, LoginRequest
from app.modules.users.models import User

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


def _hash_rate_limit_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _client_key(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return _hash_rate_limit_key(host)


def _login_key(login: str) -> str:
    return _hash_rate_limit_key(canonicalize_login(login))


def _is_rate_limited(
    database: Session,
    settings: Settings,
    login_key: str,
    client_key: str,
    now: datetime,
) -> bool:
    cutoff = now - timedelta(minutes=settings.auth_login_window_minutes)
    # On SQLite this write intentionally takes the writer lock before counting,
    # serializing concurrent login decisions and keeping check+record atomic.
    database.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at < cutoff))
    login_failures = database.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(LoginAttempt.login_key == login_key, LoginAttempt.attempted_at >= cutoff)
    )
    client_failures = database.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(LoginAttempt.client_key == client_key, LoginAttempt.attempted_at >= cutoff)
    )
    return (
        login_failures >= settings.auth_login_max_failures_per_login
        or client_failures >= settings.auth_login_max_failures_per_client
    )


def _set_auth_cookies(
    response: Response, request: Request, session_token: str, csrf_token: str
) -> None:
    settings: Settings = request.app.state.settings
    secure = settings.environment == "production"
    max_age = settings.auth_session_absolute_days * 24 * 60 * 60
    response.set_cookie(
        settings.auth_session_cookie_name,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.auth_csrf_cookie_name,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    secure = settings.environment == "production"
    response.delete_cookie(
        settings.auth_session_cookie_name,
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    response.delete_cookie(
        settings.auth_csrf_cookie_name,
        path="/",
        httponly=False,
        secure=secure,
        samesite="lax",
    )


def _invalid_credentials() -> ApiError:
    return ApiError(status.HTTP_401_UNAUTHORIZED, "invalid_credentials", "Invalid credentials")


@router.post("/login", response_model=CurrentUserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    database: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_same_origin)],
) -> User:
    settings: Settings = request.app.state.settings
    manager: PasswordManager = request.app.state.password_manager
    now = request_now(request)
    login_key = _login_key(payload.login)
    client_key = _client_key(request)
    if _is_rate_limited(database, settings, login_key, client_key, now):
        raise ApiError(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited", "Too many attempts")

    try:
        normalized_login = normalize_login(payload.login)
    except LoginFormatError:
        normalized_login = None
    user = (
        database.scalar(select(User).where(User.normalized_login == normalized_login))
        if normalized_login is not None
        else None
    )
    updated_hash = None
    if user is None:
        manager.consume_dummy_verification(payload.password)
    else:
        updated_hash = manager.verify_and_update(payload.password, user.password_hash)
    if user is None or updated_hash is None or not user.is_active:
        database.add(LoginAttempt(login_key=login_key, client_key=client_key, attempted_at=now))
        database.commit()
        raise _invalid_credentials()

    if updated_hash != user.password_hash:
        user.password_hash = updated_hash
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    database.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_secret(session_token),
            csrf_token_hash=hash_secret(csrf_token),
            created_at=now,
            last_activity_at=now,
            absolute_expires_at=now + timedelta(days=settings.auth_session_absolute_days),
        )
    )
    database.commit()
    _set_auth_cookies(response, request, session_token, csrf_token)
    return user


@router.get("/me", response_model=CurrentUserResponse)
def me(context: Annotated[AuthContext, Depends(require_auth_context)]) -> User:
    context.database.commit()
    return context.user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    database: Annotated[Session, Depends(get_db)],
    _: Annotated[None, Depends(require_same_origin)],
) -> None:
    settings: Settings = request.app.state.settings
    context = resolve_auth_context(request, database)
    if context is not None:
        require_csrf_session(request, context)
        context.session.revoked_at = request_now(request)
        database.commit()
    _clear_auth_cookies(response, settings)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    database: Annotated[Session, Depends(get_db)],
    context: Annotated[AuthContext, Depends(require_csrf_session)],
    _: Annotated[None, Depends(require_same_origin)],
) -> None:
    settings: Settings = request.app.state.settings
    manager: PasswordManager = request.app.state.password_manager
    if len(payload.new_password) < settings.auth_password_min_length:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "password_too_short",
            "Password too short",
        )
    if not manager.verify(payload.current_password, context.user.password_hash):
        raise _invalid_credentials()

    now = request_now(request)
    context.user.password_hash = manager.hash(payload.new_password)
    context.user.must_change_password = False
    database.execute(
        update(AuthSession)
        .where(AuthSession.user_id == context.user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    database.commit()
    _clear_auth_cookies(response, settings)
