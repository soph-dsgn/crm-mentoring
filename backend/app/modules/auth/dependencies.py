from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.core.config import Settings
from app.db.session import get_db
from app.modules.auth.models import AuthSession
from app.modules.users.models import User


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def request_now(request: Request) -> datetime:
    clock = getattr(request.app.state, "clock", utc_now)
    return clock()


@dataclass(frozen=True)
class AuthContext:
    session: AuthSession
    user: User
    database: Session


def resolve_auth_context(request: Request, database: Session) -> AuthContext | None:
    settings: Settings = request.app.state.settings
    token = request.cookies.get(settings.auth_session_cookie_name)
    if not token:
        return None
    auth_session = database.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_secret(token))
    )
    if auth_session is None:
        return None
    now = _naive_utc(request_now(request))
    idle_deadline = _naive_utc(auth_session.last_activity_at) + timedelta(
        days=settings.auth_session_idle_days
    )
    if (
        auth_session.revoked_at is not None
        or now >= idle_deadline
        or now >= _naive_utc(auth_session.absolute_expires_at)
    ):
        return None
    user = database.get(User, auth_session.user_id)
    if user is None or not user.is_active:
        return None
    auth_session.last_activity_at = now
    return AuthContext(session=auth_session, user=user, database=database)


def require_auth_context(
    request: Request,
    database: Annotated[Session, Depends(get_db)],
) -> AuthContext:
    context = resolve_auth_context(request, database)
    if context is None:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "not_authenticated", "Not authenticated")
    return context


def require_current_user(
    context: Annotated[AuthContext, Depends(require_auth_context)],
) -> User:
    return context.user


def require_business_user(
    user: Annotated[User, Depends(require_current_user)],
) -> User:
    if user.must_change_password:
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "password_change_required",
            "Password change required",
        )
    return user


def require_csrf_session(
    request: Request,
    context: Annotated[AuthContext, Depends(require_auth_context)],
) -> AuthContext:
    settings: Settings = request.app.state.settings
    cookie_token = request.cookies.get(settings.auth_csrf_cookie_name)
    header_token = request.headers.get("X-CSRF-Token")
    if (
        not cookie_token
        or not header_token
        or not hmac.compare_digest(cookie_token, header_token)
        or not hmac.compare_digest(hash_secret(header_token), context.session.csrf_token_hash)
    ):
        raise ApiError(status.HTTP_403_FORBIDDEN, "invalid_csrf_token", "Invalid CSRF token")
    return context


def require_same_origin(request: Request) -> None:
    if request.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
        raise ApiError(status.HTTP_403_FORBIDDEN, "cross_site_denied", "Cross-site request denied")
    origin = request.headers.get("Origin")
    settings: Settings = request.app.state.settings
    expected_origins = {str(request.base_url).rstrip("/")}
    expected_origins.update(value.rstrip("/") for value in settings.frontend_origins)
    if origin and origin.rstrip("/") not in expected_origins:
        raise ApiError(status.HTTP_403_FORBIDDEN, "cross_site_denied", "Cross-site request denied")
