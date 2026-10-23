from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditAction(enum.StrEnum):
    CURATOR_CREATED = "curator_created"
    STUDENT_ACCOUNT_CREATED = "student_account_created"
    PASSWORD_RESET = "password_reset"
    USER_DEACTIVATED = "user_deactivated"
    CURATOR_REASSIGNED = "curator_reassigned"
    CURATOR_OFFBOARDED = "curator_offboarded"
    OWNER_TRANSFERRED = "owner_transferred"


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_actor_user_id", "actor_user_id"),
        Index("ix_audit_events_target_user_id", "target_user_id"),
        Index("ix_audit_events_target_group_id", "target_group_id"),
        Index("ix_audit_events_action_created_at", "action", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    )
    target_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT", onupdate="RESTRICT"),
    )
    target_group_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("groups.id", ondelete="RESTRICT", onupdate="RESTRICT"),
    )
    action: Mapped[AuditAction] = mapped_column(
        Enum(
            AuditAction,
            name="audit_action",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    details: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
