"""Import domain models so Alembic sees every table in Base.metadata."""

from app.modules.groups.models import Group, GroupStatus
from app.modules.students.models import Student, StudentStage
from app.modules.users.models import User, UserRole

__all__ = ["Group", "GroupStatus", "Student", "StudentStage", "User", "UserRole"]
