from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
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


class StudyStatus(enum.StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    HOLD = "hold"
    DONE = "done"


class ApprovalStatus(enum.StrEnum):
    TO_SEND = "to_send"
    SENT = "sent"
    REVIEWING = "reviewing"
    REVISION = "revision"
    APPROVED = "approved"


def _enum(values: type[enum.StrEnum], name: str) -> Enum:
    return Enum(
        values,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda items: [item.value for item in items],
    )


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    student_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("students.id", ondelete="RESTRICT", onupdate="RESTRICT"), unique=True
    )
    source_metadata: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    sections: Mapped[list[StrategySection]] = relationship(
        back_populates="strategy", order_by="StrategySection.position", passive_deletes=True
    )
    tasks: Mapped[list[StrategyTask]] = relationship(
        back_populates="strategy", passive_deletes=True, overlaps="section,tasks"
    )


class StrategySection(Base):
    __tablename__ = "strategy_sections"
    __table_args__ = (
        CheckConstraint("position >= 0", name="non_negative_section_position"),
        UniqueConstraint("strategy_id", "position", name="uq_strategy_sections_position"),
        UniqueConstraint("id", "strategy_id", name="uq_strategy_sections_id_strategy"),
        Index("ix_strategy_sections_strategy_id", "strategy_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("strategies.id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    strategy: Mapped[Strategy] = relationship(back_populates="sections")
    tasks: Mapped[list[StrategyTask]] = relationship(
        back_populates="section",
        order_by="StrategyTask.position",
        passive_deletes=True,
        overlaps="strategy,tasks",
    )


class StrategyTask(Base):
    __tablename__ = "strategy_tasks"
    __table_args__ = (
        CheckConstraint("position >= 0", name="non_negative_task_position"),
        ForeignKeyConstraint(
            ["section_id", "strategy_id"],
            ["strategy_sections.id", "strategy_sections.strategy_id"],
            name="fk_strategy_tasks_section_strategy",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("section_id", "position", name="uq_strategy_tasks_position"),
        Index("ix_strategy_tasks_strategy_id", "strategy_id"),
        Index("ix_strategy_tasks_section_id", "section_id"),
        Index("ix_strategy_tasks_study_status", "study_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("strategies.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    )
    section_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    materials: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    links: Mapped[dict[str, str]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    period_text: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default=""
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    study_status: Mapped[StudyStatus] = mapped_column(
        _enum(StudyStatus, "study_status"),
        nullable=False,
        default=StudyStatus.NOT_STARTED,
        server_default=StudyStatus.NOT_STARTED.value,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    strategy: Mapped[Strategy] = relationship(back_populates="tasks", overlaps="section,tasks")
    section: Mapped[StrategySection] = relationship(
        back_populates="tasks", overlaps="strategy,tasks"
    )
    history: Mapped[list[TaskHistory]] = relationship(
        back_populates="task", order_by="TaskHistory.created_at", passive_deletes=True
    )
    approval: Mapped[AnyaApproval | None] = relationship(
        back_populates="task", uselist=False, passive_deletes=True
    )


class TaskHistory(Base):
    __tablename__ = "task_history"
    __table_args__ = (
        Index("ix_task_history_task_created", "task_id", "created_at", "id"),
        Index("ix_task_history_actor_user_id", "actor_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("strategy_tasks.id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    actor_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    task: Mapped[StrategyTask] = relationship(back_populates="history")


class AnyaApproval(Base):
    __tablename__ = "anya_approvals"
    __table_args__ = (Index("ix_anya_approvals_status", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("strategy_tasks.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        unique=True,
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        _enum(ApprovalStatus, "approval_status"),
        nullable=False,
        default=ApprovalStatus.TO_SEND,
        server_default=ApprovalStatus.TO_SEND.value,
    )
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    task: Mapped[StrategyTask] = relationship(back_populates="approval")
