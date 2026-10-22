from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.modules.groups.models import Group
from app.modules.users.models import User, UserRole, user_role_type


class StudentStage(enum.StrEnum):
    START = "start"
    PORTFOLIO = "portfolio"
    SEARCH = "search"


def student_stage_type() -> Enum:
    return Enum(
        StudentStage,
        name="student_stage",
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda values: [item.value for item in values],
    )


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "user_role"],
            ["users.id", "users.role"],
            name="fk_students_user_users",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("user_id"),
        CheckConstraint("user_role = 'student'", name="account_requires_student_role"),
        CheckConstraint("age IS NULL OR age >= 0", name="non_negative_age"),
        CheckConstraint("avatar_index >= -1", name="valid_avatar_index"),
        Index("ix_students_group_id", "group_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("groups.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[str | None] = mapped_column(String(36))
    user_role: Mapped[UserRole] = mapped_column(
        user_role_type(),
        nullable=False,
        default=UserRole.STUDENT,
        server_default=UserRole.STUDENT.value,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    age: Mapped[int | None] = mapped_column(Integer)
    photo: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    avatar_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=-1, server_default="-1"
    )
    stage: Mapped[StudentStage] = mapped_column(
        student_stage_type(), nullable=False, default=StudentStage.START, server_default="start"
    )
    stage_known: Mapped[bool | None] = mapped_column(Boolean)
    starts_at: Mapped[date | None] = mapped_column(Date)
    level: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    desired_position: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default=""
    )
    career_goal: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    links: Mapped[dict[str, str]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    background: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    experience: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    strengths: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    growth_areas: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    difficulties: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    expectations: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    personal_notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    point_a: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    point_b: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    strategy_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    group: Mapped[Group] = relationship(back_populates="students")
    user: Mapped[User | None] = relationship(back_populates="student_profile")
