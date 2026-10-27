from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LegacyImportRequest(StrictModel):
    source: dict[str, Any]
    curator_assignments: dict[str, str] = Field(default_factory=dict, max_length=500)
    confirmation_checksum: str | None = Field(default=None, min_length=64, max_length=64)
    confirm: bool = False


class ImportIssue(StrictModel):
    code: str
    entity: str
    legacy_id: str | None = None


class ValidationReport(StrictModel):
    valid: bool
    checksum: str
    source_version: int | None
    counts: dict[str, int]
    conflicts: list[ImportIssue]
    warnings: list[str]


class ImportResult(StrictModel):
    import_run_id: str
    checksum: str
    counts: dict[str, int]
    mappings: dict[str, dict[str, str]]
    idempotent_replay: bool
