from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ImportRun(Base):
    __tablename__ = "import_runs"
    __table_args__ = (Index("ix_import_runs_created_at", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source_version: Mapped[int] = mapped_column(nullable=False)
    actor_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT", onupdate="RESTRICT"), nullable=False
    )
    counts: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LegacyIdMapping(Base):
    __tablename__ = "legacy_id_mappings"
    __table_args__ = (
        UniqueConstraint("import_run_id", "entity_type", "legacy_id", name="uq_legacy_mapping"),
        Index("ix_legacy_mapping_target", "entity_type", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    import_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("import_runs.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    legacy_id: Mapped[str] = mapped_column(String(255), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
