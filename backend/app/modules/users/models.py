from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.groups.models import Group
    from app.modules.students.models import Student


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    STUDENT = "student"


def user_role_type() -> Enum:
    return Enum(
        UserRole,
        name="user_role",
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda values: [item.value for item in values],
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("login"),
        UniqueConstraint("id", "role", name="uq_users_id_role"),
        CheckConstraint("NOT is_owner OR role = 'admin'", name="owner_requires_admin_role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    login: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(user_role_type(), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    is_owner: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    curated_groups: Mapped[list[Group]] = relationship(
        back_populates="curator",
        passive_deletes=True,
    )
    student_profile: Mapped[Student | None] = relationship(
        back_populates="user",
        passive_deletes=True,
        uselist=False,
    )
