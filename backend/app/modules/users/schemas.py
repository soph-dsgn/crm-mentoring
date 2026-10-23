from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.users.models import UserRole


class LoginAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str = Field(min_length=1, max_length=255)


class ReassignCuratorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    curator_id: str = Field(min_length=1, max_length=36)


class OffboardCuratorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    successor_curator_id: str = Field(min_length=1, max_length=36)


class SafeUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    login: str
    role: UserRole
    is_owner: bool
    is_active: bool
    must_change_password: bool
    created_at: datetime
    deactivated_at: datetime | None


class CuratorPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    login: str
    role: UserRole
    is_owner: bool
    is_active: bool


class TemporaryCredentialResponse(BaseModel):
    user: SafeUserResponse
    temporary_password: str


class StudentAccountResponse(BaseModel):
    student_id: str
    user: SafeUserResponse


class StudentTemporaryCredentialResponse(StudentAccountResponse):
    temporary_password: str


class PasswordResetResponse(BaseModel):
    user_id: str
    must_change_password: bool
    temporary_password: str


class GroupAssignmentResponse(BaseModel):
    group_id: str
    curator_id: str


class OffboardResponse(BaseModel):
    user: SafeUserResponse
    reassigned_group_ids: list[str]
