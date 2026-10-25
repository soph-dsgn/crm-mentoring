"""Import domain models so Alembic sees every table in Base.metadata."""

from app.modules.auth.models import AuthSession, LoginAttempt
from app.modules.groups.models import Group, GroupStatus
from app.modules.homeworks.models import Homework, HomeworkHistory, HomeworkItem, HomeworkStatus
from app.modules.meetings.models import Meeting
from app.modules.strategies.models import (
    AnyaApproval,
    ApprovalStatus,
    ReviewStatus,
    Strategy,
    StrategySection,
    StrategyTask,
    StudyStatus,
    TaskHistory,
)
from app.modules.students.models import Student, StudentStage
from app.modules.users.audit import AuditAction, AuditEvent
from app.modules.users.models import User, UserRole

__all__ = [
    "AuditAction",
    "AuditEvent",
    "AuthSession",
    "Group",
    "GroupStatus",
    "Homework",
    "HomeworkHistory",
    "HomeworkItem",
    "HomeworkStatus",
    "LoginAttempt",
    "Meeting",
    "Student",
    "StudentStage",
    "Strategy",
    "StrategySection",
    "StrategyTask",
    "StudyStatus",
    "ReviewStatus",
    "TaskHistory",
    "AnyaApproval",
    "ApprovalStatus",
    "User",
    "UserRole",
]
