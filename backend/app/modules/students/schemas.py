from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

from app.modules.students.models import StudentStage

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
ShortText = Annotated[str, StringConstraints(max_length=255)]
LongText = Annotated[str, StringConstraints(max_length=20_000)]
Photo = Annotated[str, StringConstraints(max_length=2_048)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StudentFields(StrictModel):
    name: Name
    age: int | None = Field(default=None, ge=0, le=150)
    photo: Photo = ""
    avatar_index: int = Field(default=-1, ge=-1, le=10_000)
    stage: StudentStage = StudentStage.START
    stage_known: bool | None = None
    starts_at: date | None = None
    level: ShortText = ""
    desired_position: ShortText = ""
    career_goal: LongText = ""
    links: dict[ShortText, HttpUrl] = Field(default_factory=dict, max_length=50)
    background: LongText = ""
    experience: LongText = ""
    strengths: LongText = ""
    growth_areas: LongText = ""
    difficulties: LongText = ""
    expectations: LongText = ""
    personal_notes: LongText = ""
    point_a: LongText = ""
    point_b: LongText = ""
    notes: LongText = ""


class StudentCreate(StudentFields):
    pass


class StudentUpdate(StrictModel):
    expected_version: int = Field(ge=1)
    name: Name | None = None
    age: int | None = Field(default=None, ge=0, le=150)
    photo: Photo | None = None
    avatar_index: int | None = Field(default=None, ge=-1, le=10_000)
    stage: StudentStage | None = None
    stage_known: bool | None = None
    starts_at: date | None = None
    level: ShortText | None = None
    desired_position: ShortText | None = None
    career_goal: LongText | None = None
    links: dict[ShortText, HttpUrl] | None = Field(default=None, max_length=50)
    background: LongText | None = None
    experience: LongText | None = None
    strengths: LongText | None = None
    growth_areas: LongText | None = None
    difficulties: LongText | None = None
    expectations: LongText | None = None
    personal_notes: LongText | None = None
    point_a: LongText | None = None
    point_b: LongText | None = None
    notes: LongText | None = None

    @model_validator(mode="after")
    def validate_mutation(self) -> StudentUpdate:
        non_nullable = {
            "name",
            "photo",
            "avatar_index",
            "stage",
            "level",
            "desired_position",
            "career_goal",
            "links",
            "background",
            "experience",
            "strengths",
            "growth_areas",
            "difficulties",
            "expectations",
            "personal_notes",
            "point_a",
            "point_b",
            "notes",
        }
        if any(getattr(self, field) is None for field in non_nullable & self.model_fields_set):
            raise ValueError("Non-nullable student fields cannot be null")
        if self.model_fields_set == {"expected_version"}:
            raise ValueError("At least one field must be changed")
        return self


class VersionRequest(StrictModel):
    expected_version: int = Field(ge=1)


class StudentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    group_id: str
    name: str
    stage: StudentStage
    archived_at: datetime | None
    updated_at: datetime
    version: int


class StudentRead(StudentSummary):
    user_id: str | None
    age: int | None
    photo: str
    avatar_index: int
    stage_known: bool | None
    starts_at: date | None
    level: str
    desired_position: str
    career_goal: str
    links: dict[str, str]
    background: str
    experience: str
    strengths: str
    growth_areas: str
    difficulties: str
    expectations: str
    personal_notes: str
    point_a: str
    point_b: str
    notes: str
    strategy_updated_at: datetime
    created_at: datetime


class StudentSelfRead(StudentSummary):
    age: int | None
    photo: str
    avatar_index: int
    stage_known: bool | None
    starts_at: date | None
    level: str
    desired_position: str
    career_goal: str
    links: dict[str, str]
    background: str
    experience: str
    strengths: str
    growth_areas: str
    difficulties: str
    expectations: str
    point_a: str
    point_b: str
    strategy_updated_at: datetime
    created_at: datetime


class StudentList(BaseModel):
    items: list[StudentSummary]
    next_cursor: str | None
