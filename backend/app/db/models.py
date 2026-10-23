"""Import domain models so Alembic sees every table in Base.metadata."""

from app.modules.auth.models import AuthSession, LoginAttempt
from app.modules.groups.models import Group, GroupStatus
from app.modules.students.models import Student, StudentStage
from app.modules.users.audit import AuditAction, AuditEvent
from app.modules.users.models import User, UserRole

__all__ = [
    "AuditAction",
    "AuditEvent",
    "AuthSession",
    "Group",
    "GroupStatus",
    "LoginAttempt",
    "Student",
    "StudentStage",
    "User",
    "UserRole",
]
