from pydantic import BaseModel, Field

from app.modules.users.models import UserRole


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class CurrentUserResponse(BaseModel):
    id: str
    login: str
    role: UserRole
    is_owner: bool
    must_change_password: bool
    is_active: bool
