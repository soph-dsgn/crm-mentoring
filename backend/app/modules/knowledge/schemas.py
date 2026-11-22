from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.modules.knowledge.models import KnowledgeKind

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
