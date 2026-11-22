from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.modules.knowledge.models import (
    KnowledgeImportMode,
    KnowledgeKind,
    KnowledgeLibraryStatus,
    KnowledgeSourceFormat,
)

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Category = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Html = Annotated[str, StringConstraints(min_length=1, max_length=500_000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnowledgeCreate(StrictModel):
    kind: KnowledgeKind
    title: Title
    category: Category | None = None
    html: Html
    position: int = Field(default=0, ge=0, le=1_000_000)


class KnowledgeUpdate(StrictModel):
    expected_version: int = Field(ge=1)
    title: Title | None = None
    category: Category | None = None
    html: Html | None = None
    position: int | None = Field(default=None, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def validate_mutation(self) -> KnowledgeUpdate:
        non_nullable = {"title", "html", "position"}
        if any(getattr(self, field) is None for field in non_nullable & self.model_fields_set):
            raise ValueError("Non-nullable Knowledge fields cannot be null")
        if self.model_fields_set == {"expected_version"}:
            raise ValueError("At least one field must be changed")
        return self


class VersionRequest(StrictModel):
    expected_version: int = Field(ge=1)


class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: KnowledgeKind
    title: str
    category: str | None
    html: str
    plain_text: str
    position: int
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int
    is_favorite: bool


class KnowledgeDocumentSummary(BaseModel):
    id: str
    kind: KnowledgeKind
    title: str
    category: str | None
    excerpt: str
    position: int
    archived_at: datetime | None
    updated_at: datetime
    version: int
    is_favorite: bool


class KnowledgeDocumentList(BaseModel):
    items: list[KnowledgeDocumentSummary]
    next_cursor: str | None


class KnowledgeConflictResolution(StrictModel):
    action: Literal["skip", "create_copy", "overwrite"]
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_expected_version(self) -> KnowledgeConflictResolution:
        if (self.action == "overwrite") != (self.expected_version is not None):
            raise ValueError("overwrite requires expected_version and other actions forbid it")
        return self


class KnowledgeImportRequest(StrictModel):
    source: dict[str, Any]
    source_format: KnowledgeSourceFormat
    mode: KnowledgeImportMode
    resolutions: dict[str, KnowledgeConflictResolution] = Field(
        default_factory=dict, max_length=5000
    )
    confirmation_checksum: str | None = Field(
        default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    confirm: bool = False


class KnowledgeImportIssue(StrictModel):
    code: str
    source_key: str | None = None
    fields: list[str] = Field(default_factory=list)


class KnowledgeImportItem(StrictModel):
    source_key: str
    classification: Literal[
        "new", "archived", "exact_duplicate", "conflict", "overwrite", "skipped"
    ]
    target_id: str | None = None
    conflict_code: str | None = None
    resolved: bool = False


class KnowledgeImportValidation(StrictModel):
    valid: bool
    checksum: str
    source_version: int | None
    source_format: KnowledgeSourceFormat
    mode: KnowledgeImportMode
    library_status: KnowledgeLibraryStatus
    counts: dict[str, int]
    items: list[KnowledgeImportItem]
    issues: list[KnowledgeImportIssue]


class KnowledgeImportResult(StrictModel):
    import_run_id: str
    checksum: str
    counts: dict[str, int]
    mappings: dict[str, str]
    library_status: KnowledgeLibraryStatus
    idempotent_replay: bool


class KnowledgeLibraryStateRead(StrictModel):
    status: KnowledgeLibraryStatus
    version: int
    activated_at: datetime | None


class KnowledgeExportDocument(StrictModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    kind: KnowledgeKind
    title: str
    category: str | None
    html: str
    plain_text: str
    position: int
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class KnowledgeExportFavorite(StrictModel):
    user_id: str
    document_id: str


class KnowledgeExportImportRun(StrictModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    checksum: str
    request_checksum: str
    source_version: int
    source_format: KnowledgeSourceFormat
    mode: KnowledgeImportMode
    actor_user_id: str
    counts: dict[str, int]
    created_at: datetime


class KnowledgeExportMapping(StrictModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    import_run_id: str
    source_key: str
    source_fingerprint: str
    target_id: str


class KnowledgeLogicalExport(StrictModel):
    schema_version: Literal[1] = 1
    exported_at: datetime
    library: KnowledgeLibraryStateRead
    documents: list[KnowledgeExportDocument]
    favorites: list[KnowledgeExportFavorite]
    import_runs: list[KnowledgeExportImportRun]
    mappings: list[KnowledgeExportMapping]
