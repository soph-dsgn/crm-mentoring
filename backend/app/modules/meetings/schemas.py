from __future__ import annotations

from datetime import date as DateValue
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
LongText = Annotated[str, StringConstraints(max_length=20_000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MeetingCreate(StrictModel):
    date: DateValue
    title: Title
    summary: LongText = ""
    notes: LongText = ""


class MeetingUpdate(StrictModel):
    expected_version: int = Field(ge=1)
    date: DateValue | None = None
    title: Title | None = None
    summary: LongText | None = None
    notes: LongText | None = None

    @model_validator(mode="after")
    def validate_mutation(self) -> MeetingUpdate:
        fields = self.model_fields_set - {"expected_version"}
        if not fields:
            raise ValueError("At least one field must be changed")
        if any(getattr(self, field) is None for field in fields):
            raise ValueError("Meeting fields cannot be null")
        return self


class MeetingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    date: DateValue
    title: str
    summary: str
    notes: str
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class MeetingSelfRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    date: DateValue
    title: str
    summary: str
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class MeetingList(BaseModel):
    items: list[MeetingRead]
    next_cursor: str | None


class MeetingSelfList(BaseModel):
    items: list[MeetingSelfRead]
    next_cursor: str | None
