from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

from app.modules.strategies.models import ApprovalStatus, ReviewStatus, StudyStatus

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
LongText = Annotated[str, StringConstraints(max_length=20_000)]
ShortText = Annotated[str, StringConstraints(max_length=255)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrategyCreate(StrictModel):
    source_metadata: dict[ShortText, object] = Field(default_factory=dict, max_length=50)


class StrategyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    source_metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime
    version: int


class SectionCreate(StrictModel):
    title: Title
    position: int = Field(ge=0, le=10_000)


class SectionUpdate(StrictModel):
    expected_version: int = Field(ge=1)
    title: Title


class SectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_id: str
    title: str
    position: int
    created_at: datetime
    updated_at: datetime
    version: int


class ReorderItem(StrictModel):
    id: str = Field(min_length=1, max_length=36)
    expected_version: int = Field(ge=1)
    position: int = Field(ge=0, le=10_000)


class SectionReorder(StrictModel):
    items: list[ReorderItem] = Field(min_length=1, max_length=500)


class TaskCreate(StrictModel):
    title: Title
    description: LongText = ""
    materials: list[ShortText] = Field(default_factory=list, max_length=100)
    links: dict[ShortText, HttpUrl] = Field(default_factory=dict, max_length=50)
    blocker: bool = False
    period_text: ShortText = ""
    due_at: datetime | None = None
    position: int = Field(ge=0, le=10_000)


class TaskUpdate(StrictModel):
    expected_version: int = Field(ge=1)
    title: Title | None = None
    description: LongText | None = None
    materials: list[ShortText] | None = Field(default=None, max_length=100)
    links: dict[ShortText, HttpUrl] | None = Field(default=None, max_length=50)
    blocker: bool | None = None
    period_text: ShortText | None = None
    due_at: datetime | None = None

    @model_validator(mode="after")
    def validate_mutation(self) -> TaskUpdate:
        non_nullable = {"title", "description", "materials", "links", "period_text", "blocker"}
        if any(getattr(self, field) is None for field in non_nullable & self.model_fields_set):
            raise ValueError("Non-nullable task fields cannot be null")
        if self.model_fields_set == {"expected_version"}:
            raise ValueError("At least one field must be changed")
        return self


class TaskStatusChange(StrictModel):
    expected_version: int = Field(ge=1)
    study_status: StudyStatus


class VersionRequest(StrictModel):
    expected_version: int = Field(ge=1)


class TaskMove(VersionRequest):
    target_section_id: str = Field(min_length=1, max_length=36)


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    strategy_id: str
    section_id: str
    title: str
    description: str
    materials: list[str]
    links: dict[str, str]
    blocker: bool
    period_text: str
    due_at: datetime | None
    position: int
    study_status: StudyStatus
    review_status: ReviewStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class HistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    actor_user_id: str
    event_type: str
    details: dict[str, object]
    created_at: datetime


class HistoryList(BaseModel):
    items: list[HistoryRead]
    next_cursor: str | None


class HistorySelfRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    event_type: str
    details: dict[str, object]
    created_at: datetime


class HistorySelfList(BaseModel):
    items: list[HistorySelfRead]
    next_cursor: str | None


class ApprovalCreate(StrictModel):
    comment: LongText = ""


class ApprovalTransition(StrictModel):
    expected_version: int = Field(ge=1)
    status: ApprovalStatus
    comment: LongText | None = None


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    status: ApprovalStatus
    comment: str
    created_at: datetime
    updated_at: datetime
    version: int


class ApprovalList(BaseModel):
    items: list[ApprovalRead]
    next_cursor: str | None


class ImportedTask(StrictModel):
    title: Title
    description: LongText = ""
    period_text: ShortText = ""
    materials: list[ShortText] = Field(default_factory=list, max_length=100)
    study_status: StudyStatus = StudyStatus.NOT_STARTED


class ImportedSection(StrictModel):
    title: Title
    tasks: list[ImportedTask] = Field(min_length=1, max_length=500)


class ImportedProfile(StrictModel):
    point_a: LongText | None = None
    point_b: LongText | None = None
    telegram: HttpUrl | None = None


class ImportWarning(BaseModel):
    code: str
    count: int
    examples: list[str] = Field(default_factory=list)


class StrategyImportDraft(BaseModel):
    source_title: str
    sha256: str
    page_count: int
    profile: ImportedProfile
    sections: list[ImportedSection]
    warnings: list[ImportWarning]


class ImportSource(StrictModel):
    file_name: ShortText = ""
    title: ShortText = ""
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class StrategyImportApply(StrictModel):
    expected_version: int = Field(ge=1)
    source: ImportSource
    profile: ImportedProfile = Field(default_factory=ImportedProfile)
    sections: list[ImportedSection] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_size(self) -> StrategyImportApply:
        if sum(len(section.tasks) for section in self.sections) > 2000:
            raise ValueError("Too many tasks in one import")
        return self


class StrategyImportResult(BaseModel):
    strategy: StrategyRead
    student_version: int
    section_count: int
    task_count: int
