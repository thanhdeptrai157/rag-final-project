from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class UserCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            raise ValueError("Invalid email address")
        return email


class UserLogin(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class GoogleLogin(BaseModel):
    id_token: str = Field(..., min_length=10)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)


class UserResponse(BaseModel):
    user_id: UUID
    email: str
    full_name: str | None = None
    auth_provider: str
    avatar_url: str | None = None
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
