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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeKind(enum.StrEnum):
    PROMPT = "prompt"
    CHAPTER = "chapter"


class KnowledgeLibraryStatus(enum.StrEnum):
    PENDING = "pending"
    ACTIVE = "active"


class KnowledgeImportMode(enum.StrEnum):
    INITIAL = "initial"
    ADDITIONAL = "additional"


class KnowledgeSourceFormat(enum.StrEnum):
    KNOWLEDGE_DATA_V1 = "knowledge_data_v1"
    PARSED_DOCUMENTS = "parsed_documents"


def knowledge_kind_type() -> Enum:
    return Enum(
        KnowledgeKind,
        name="knowledge_kind",
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda values: [item.value for item in values],
    )


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint("version >= 1", name="version"),
        CheckConstraint("position >= 0", name="position"),
        Index("ix_knowledge_documents_kind_archived", "kind", "archived_at"),
        Index("ix_knowledge_documents_category", "category"),
        Index("ix_knowledge_documents_updated_id", "updated_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind: Mapped[KnowledgeKind] = mapped_column(knowledge_kind_type(), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    html: Mapped[str] = mapped_column(Text, nullable=False)
    plain_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_by_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    )
    updated_by_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class KnowledgeFavorite(Base):
    __tablename__ = "knowledge_favorites"
    __table_args__ = (Index("ix_knowledge_favorites_document_id", "document_id"),)

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE", onupdate="RESTRICT"),
        primary_key=True,
    )
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE", onupdate="RESTRICT"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeLibraryState(Base):
    __tablename__ = "knowledge_library_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("version >= 1", name="version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    status: Mapped[KnowledgeLibraryStatus] = mapped_column(
        Enum(
            KnowledgeLibraryStatus,
            name="knowledge_library_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=False,
        default=KnowledgeLibraryStatus.PENDING,
        server_default=KnowledgeLibraryStatus.PENDING.value,
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT", onupdate="RESTRICT")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class KnowledgeImportRun(Base):
    __tablename__ = "knowledge_import_runs"
    __table_args__ = (Index("ix_knowledge_import_runs_created_at", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    request_checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_format: Mapped[KnowledgeSourceFormat] = mapped_column(
        Enum(
            KnowledgeSourceFormat,
            name="knowledge_source_format",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=False,
    )
    mode: Mapped[KnowledgeImportMode] = mapped_column(
        Enum(
            KnowledgeImportMode,
            name="knowledge_import_mode",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=False,
    )
    actor_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT", onupdate="RESTRICT"), nullable=False
    )
    counts: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeImportMapping(Base):
    __tablename__ = "knowledge_import_mappings"
    __table_args__ = (
        CheckConstraint("length(source_key) > 0", name="source_key_not_empty"),
        UniqueConstraint("import_run_id", "source_key", name="uq_knowledge_import_mapping_source"),
        Index("ix_knowledge_import_mappings_source_key", "source_key"),
        Index("ix_knowledge_import_mappings_target_id", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    import_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_import_runs.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    )
    source_key: Mapped[str] = mapped_column(String(768), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_documents.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
