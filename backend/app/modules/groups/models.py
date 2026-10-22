from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.users.models import User, UserRole, user_role_type

if TYPE_CHECKING:
    from app.modules.students.models import Student


class GroupStatus(enum.StrEnum):
    BACKLOG = "backlog"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


def group_status_type(name: str = "group_status") -> Enum:
    return Enum(
        GroupStatus,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda values: [item.value for item in values],
    )


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (
        ForeignKeyConstraint(
            ["curator_id", "curator_role"],
            ["users.id", "users.role"],
            name="fk_groups_curator_users",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        CheckConstraint("curator_role = 'admin'", name="curator_requires_admin_role"),
        CheckConstraint(
            "ends_at IS NULL OR starts_at <= ends_at",
            name="planned_dates_in_order",
        ),
        CheckConstraint(
            "duration_months IS NULL OR duration_months > 0",
            name="positive_duration_months",
        ),
        Index("ix_groups_curator_id", "curator_id"),
        Index("ix_groups_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    curator_id: Mapped[str] = mapped_column(String(36), nullable=False)
    curator_role: Mapped[UserRole] = mapped_column(
        user_role_type(),
        nullable=False,
        default=UserRole.ADMIN,
        server_default=UserRole.ADMIN.value,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[date] = mapped_column(Date, nullable=False)
    ends_at: Mapped[date | None] = mapped_column(Date)
    actual_ends_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[GroupStatus] = mapped_column(
        group_status_type(), nullable=False, default=GroupStatus.BACKLOG
    )
    status_before_archive: Mapped[GroupStatus | None] = mapped_column(
        group_status_type("previous_group_status")
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    duration_months: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    curator: Mapped[User] = relationship(back_populates="curated_groups")
    students: Mapped[list[Student]] = relationship(
        back_populates="group",
        passive_deletes=True,
    )
