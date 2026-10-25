from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterRequest(BaseModel):
    """User registration payload."""

    email: EmailStr = Field(description="Unique email address")
    password: str = Field(min_length=8, max_length=128, description="Password with minimum 8 characters")
    full_name: str = Field(min_length=2, max_length=100, description="Full legal or professional name")


class UserLoginRequest(BaseModel):
    """User credentials payload."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    """Sanitized user account schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime


class AuthResponse(BaseModel):
    """Authentication success payload."""

    user: UserResponse
    token: str
    token_type: str = "Bearer"
    expires_at: datetime
    message: str = "Authentication successful"


class MessageResponse(BaseModel):
    """Generic status response."""

    message: str
    success: bool = True
