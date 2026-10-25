from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DDL,
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.strategies.models import StrategyTask


class HomeworkStatus(enum.StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    PROGRESS = "progress"
    SUBMITTED = "submitted"
    REVISION = "revision"
    ACCEPTED = "accepted"


def homework_status_type(name: str = "homework_status") -> Enum:
    return Enum(
        HomeworkStatus,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda values: [item.value for item in values],
    )


class Homework(Base):
    __tablename__ = "homeworks"
    __table_args__ = (
        UniqueConstraint("id", "strategy_id", name="uq_homeworks_id_strategy"),
        Index("ix_homeworks_strategy_status", "strategy_id", "status"),
        Index("ix_homeworks_archived_at", "archived_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("strategies.id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    links: Mapped[dict[str, str]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    submission_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    submission_links: Mapped[dict[str, str]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    curator_feedback: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[HomeworkStatus] = mapped_column(
        homework_status_type(),
        nullable=False,
        default=HomeworkStatus.DRAFT,
        server_default=HomeworkStatus.DRAFT.value,
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    items: Mapped[list[HomeworkItem]] = relationship(
        back_populates="homework", order_by="HomeworkItem.position", passive_deletes=True
    )
    history: Mapped[list[HomeworkHistory]] = relationship(
        back_populates="homework", order_by="HomeworkHistory.created_at", passive_deletes=True
    )


class HomeworkItem(Base):
    __tablename__ = "homework_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["homework_id", "strategy_id"],
            ["homeworks.id", "homeworks.strategy_id"],
            name="fk_homework_items_homework_strategy",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        UniqueConstraint("homework_id", "task_id", name="uq_homework_items_task"),
        UniqueConstraint("homework_id", "position", name="uq_homework_items_position"),
        Index("ix_homework_items_task_id", "task_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    homework_id: Mapped[str] = mapped_column(String(36), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("strategy_tasks.id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    homework: Mapped[Homework] = relationship(back_populates="items")
    task: Mapped[StrategyTask] = relationship()


class HomeworkHistory(Base):
    __tablename__ = "homework_history"
    __table_args__ = (
        Index("ix_homework_history_homework_created", "homework_id", "created_at", "id"),
        Index("ix_homework_history_actor_user_id", "actor_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    homework_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("homeworks.id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    actor_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[HomeworkStatus | None] = mapped_column(
        homework_status_type("homework_history_from_status")
    )
    to_status: Mapped[HomeworkStatus | None] = mapped_column(
        homework_status_type("homework_history_to_status")
    )
    details: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    homework: Mapped[Homework] = relationship(back_populates="history")


event.listen(
    HomeworkItem.__table__,
    "after_create",
    DDL(
        """
        CREATE TRIGGER trg_homework_items_strategy_insert
        BEFORE INSERT ON homework_items
        WHEN (SELECT strategy_id FROM strategy_tasks WHERE id = NEW.task_id) != NEW.strategy_id
        BEGIN
            SELECT RAISE(ABORT, 'homework_item_strategy_mismatch');
        END
        """
    ).execute_if(dialect="sqlite"),
)
for table in (HomeworkItem.__table__, HomeworkHistory.__table__):
    for operation in ("UPDATE", "DELETE"):
        event.listen(
            table,
            "after_create",
            DDL(
                f"""
                CREATE TRIGGER trg_{table.name}_append_only_{operation.lower()}
                BEFORE {operation} ON {table.name}
                BEGIN
                    SELECT RAISE(ABORT, '{table.name}_append_only');
                END
                """
            ).execute_if(dialect="sqlite"),
        )
