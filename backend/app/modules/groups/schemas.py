from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.modules.groups.models import GroupStatus

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Notes = Annotated[str, StringConstraints(max_length=20_000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GroupCreate(StrictModel):
    name: Name
    starts_at: date
    ends_at: date | None = None
    actual_ends_at: date | None = None
    status: GroupStatus = GroupStatus.BACKLOG
    notes: Notes = ""
    duration_months: Decimal | None = Field(default=None, gt=0, le=120)

    @model_validator(mode="after")
    def validate_dates_and_status(self) -> GroupCreate:
        if self.ends_at is not None and self.starts_at > self.ends_at:
            raise ValueError("ends_at must not precede starts_at")
        if self.actual_ends_at is not None and self.starts_at > self.actual_ends_at:
            raise ValueError("actual_ends_at must not precede starts_at")
        if self.status is GroupStatus.ARCHIVED:
            raise ValueError("Use the archive endpoint")
        return self


class GroupUpdate(StrictModel):
    expected_version: int = Field(ge=1)
    name: Name | None = None
    starts_at: date | None = None
    ends_at: date | None = None
    actual_ends_at: date | None = None
    status: GroupStatus | None = None
    notes: Notes | None = None
    duration_months: Decimal | None = Field(default=None, gt=0, le=120)

    @model_validator(mode="after")
    def validate_mutation(self) -> GroupUpdate:
        required = {"name", "starts_at", "status", "notes"}
        if any(getattr(self, field) is None for field in required & self.model_fields_set):
            raise ValueError("Non-nullable group fields cannot be null")
        if self.status is GroupStatus.ARCHIVED:
            raise ValueError("Use the archive endpoint")
        if self.model_fields_set == {"expected_version"}:
            raise ValueError("At least one field must be changed")
        return self


class VersionRequest(StrictModel):
    expected_version: int = Field(ge=1)


class GroupSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    curator_id: str
    name: str
    starts_at: date
    ends_at: date | None
    status: GroupStatus
    updated_at: datetime
    version: int


class GroupRead(GroupSummary):
    actual_ends_at: date | None
    status_before_archive: GroupStatus | None
    notes: str
    duration_months: Decimal | None
    created_at: datetime


class GroupStudentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    starts_at: date
    ends_at: date | None
    actual_ends_at: date | None
    status: GroupStatus
    version: int


class GroupList(BaseModel):
    items: list[GroupSummary]
    next_cursor: str | None


class GroupStudentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    starts_at: date
    ends_at: date | None
    status: GroupStatus
    updated_at: datetime
    version: int


class GroupStudentList(BaseModel):
    items: list[GroupStudentSummary]
    next_cursor: str | None
