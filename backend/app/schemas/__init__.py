"""Pydantic schemas package."""

from app.schemas.auth import (
    AuthResponse,
    MessageResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.schemas.health import HealthResponse
from app.schemas.profile import (
    CertificationCreateRequest,
    CertificationResponse,
    EducationCreateRequest,
    EducationResponse,
    ExperienceCreateRequest,
    ExperienceResponse,
    FullCandidateProfileResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    ProjectCreateRequest,
    ProjectResponse,
    SkillCreateRequest,
    SkillResponse,
)

__all__ = [
    "HealthResponse",
    "UserRegisterRequest",
    "UserLoginRequest",
    "UserResponse",
    "AuthResponse",
    "MessageResponse",
    "ProfileUpdateRequest",
    "ProfileResponse",
    "SkillCreateRequest",
    "SkillResponse",
    "EducationCreateRequest",
    "EducationResponse",
    "ExperienceCreateRequest",
    "ExperienceResponse",
    "ProjectCreateRequest",
    "ProjectResponse",
    "CertificationCreateRequest",
    "CertificationResponse",
    "FullCandidateProfileResponse",
]
