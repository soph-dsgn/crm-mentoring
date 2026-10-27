from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, func
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
    GROUP_CREATED = "group_created"
    GROUP_UPDATED = "group_updated"
    GROUP_ARCHIVED = "group_archived"
    GROUP_RESTORED = "group_restored"
    STUDENT_CREATED = "student_created"
    STUDENT_UPDATED = "student_updated"
    STUDENT_ARCHIVED = "student_archived"
    STUDENT_RESTORED = "student_restored"
    STRATEGY_CREATED = "strategy_created"
    SECTION_CREATED = "section_created"
    SECTION_UPDATED = "section_updated"
    SECTIONS_REORDERED = "sections_reordered"
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_STATUS_CHANGED = "task_status_changed"
    TASK_ARCHIVED = "task_archived"
    TASK_RESTORED = "task_restored"
    APPROVAL_CREATED = "approval_created"
    APPROVAL_CHANGED = "approval_changed"
    MEETING_CREATED = "meeting_created"
    MEETING_UPDATED = "meeting_updated"
    MEETING_ARCHIVED = "meeting_archived"
    MEETING_RESTORED = "meeting_restored"
    HOMEWORK_CREATED = "homework_created"
    HOMEWORK_UPDATED = "homework_updated"
    HOMEWORK_TRANSITIONED = "homework_transitioned"
    HOMEWORK_ARCHIVED = "homework_archived"
    HOMEWORK_RESTORED = "homework_restored"
    LEGACY_IMPORTED = "legacy_imported"


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
    action: Mapped[AuditAction] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    details: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
