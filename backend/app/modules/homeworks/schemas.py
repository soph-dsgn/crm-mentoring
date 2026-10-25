from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

from app.modules.homeworks.models import HomeworkStatus

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
LongText = Annotated[str, StringConstraints(max_length=20_000)]
ShortText = Annotated[str, StringConstraints(max_length=255)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HomeworkCreate(StrictModel):
    title: Title
    description: LongText = ""
    task_ids: list[str] = Field(min_length=1, max_length=100)
    links: dict[ShortText, HttpUrl] = Field(default_factory=dict, max_length=50)
    due_at: datetime | None = None


class HomeworkUpdate(StrictModel):
    expected_version: int = Field(ge=1)
    title: Title | None = None
    description: LongText | None = None
    links: dict[ShortText, HttpUrl] | None = Field(default=None, max_length=50)
    due_at: datetime | None = None

    @model_validator(mode="after")
    def validate_mutation(self) -> HomeworkUpdate:
        fields = self.model_fields_set - {"expected_version"}
        if not fields:
            raise ValueError("At least one field must be changed")
        if any(getattr(self, field) is None for field in fields - {"due_at"}):
            raise ValueError("Homework fields cannot be null")
        return self


class HomeworkTransition(StrictModel):
    expected_version: int = Field(ge=1)
    status: HomeworkStatus
    submission_text: LongText | None = None
    submission_links: dict[ShortText, HttpUrl] | None = Field(default=None, max_length=50)
    curator_feedback: LongText | None = None


class HomeworkItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    position: int
    title: str
    description: str
    materials: list[str]
    links: dict[str, str]
    period_text: str
    due_at: datetime | None


class HomeworkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_id: str
    title: str
    description: str
    links: dict[str, str]
    submission_text: str
    submission_links: dict[str, str]
    curator_feedback: str
    due_at: datetime | None
    status: HomeworkStatus
    issued_at: datetime | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int
    items: list[HomeworkItemRead]


class HomeworkList(BaseModel):
    items: list[HomeworkRead]
    next_cursor: str | None


class HomeworkHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    homework_id: str
    actor_user_id: str
    event_type: str
    from_status: HomeworkStatus | None
    to_status: HomeworkStatus | None
    details: dict[str, object]
    created_at: datetime


class HomeworkHistorySelfRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    homework_id: str
    event_type: str
    from_status: HomeworkStatus | None
    to_status: HomeworkStatus | None
    details: dict[str, object]
    created_at: datetime


class HomeworkHistoryList(BaseModel):
    items: list[HomeworkHistoryRead]
    next_cursor: str | None


class HomeworkHistorySelfList(BaseModel):
    items: list[HomeworkHistorySelfRead]
    next_cursor: str | None
