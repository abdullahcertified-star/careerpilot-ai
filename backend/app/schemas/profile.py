from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ProfileUpdateRequest(BaseModel):
    """Candidate profile update request schema."""

    headline: Optional[str] = Field(default=None, max_length=255)
    bio: Optional[str] = Field(default=None, max_length=4000)
    location: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)
    github_url: Optional[str] = Field(default=None, max_length=255)
    linkedin_url: Optional[str] = Field(default=None, max_length=255)
    website_url: Optional[str] = Field(default=None, max_length=255)
    target_job_titles: Optional[List[str]] = Field(default=None)
    target_salary_min: Optional[int] = Field(default=None, ge=0)
    target_salary_max: Optional[int] = Field(default=None, ge=0)
    remote_preference: Optional[str] = Field(default=None, max_length=50)
    work_authorization_status: Optional[str] = Field(default=None, max_length=100)


class ProfileResponse(BaseModel):
    """Candidate profile schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    headline: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    website_url: Optional[str] = None
    target_job_titles: List[str] = []
    target_salary_min: Optional[int] = None
    target_salary_max: Optional[int] = None
    remote_preference: str = "flexible"
    work_authorization_status: Optional[str] = None
    profile_version: int = 1
    created_at: datetime
    updated_at: datetime


class SkillCreateRequest(BaseModel):
    """Candidate skill creation schema."""

    name: str = Field(min_length=1, max_length=100)
    category: str = Field(default="technical", max_length=50)
    proficiency_level: str = Field(default="intermediate", max_length=50)
    years_experience: float = Field(default=1.0, ge=0.0)


class SkillResponse(BaseModel):
    """Candidate skill schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    category: str
    proficiency_level: str
    years_experience: float
    created_at: datetime


class EducationCreateRequest(BaseModel):
    """Education creation schema."""

    institution: str = Field(min_length=1, max_length=255)
    degree: str = Field(min_length=1, max_length=100)
    field_of_study: str = Field(min_length=1, max_length=150)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_current: bool = False
    gpa: Optional[str] = None


class EducationResponse(BaseModel):
    """Education response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    institution: str
    degree: str
    field_of_study: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_current: bool
    gpa: Optional[str] = None
    created_at: datetime


class ExperienceCreateRequest(BaseModel):
    """Experience creation schema."""

    company: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=150)
    location: Optional[str] = Field(default=None, max_length=150)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_current: bool = False
    description: Optional[str] = None
    achievements: List[str] = Field(default_factory=list)


class ExperienceResponse(BaseModel):
    """Experience response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    company: str
    title: str
    location: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_current: bool
    description: Optional[str] = None
    achievements: List[str] = []
    created_at: datetime


class ProjectCreateRequest(BaseModel):
    """Project creation schema."""

    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    url: Optional[str] = None
    repo_url: Optional[str] = None
    technologies: List[str] = Field(default_factory=list)
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class ProjectResponse(BaseModel):
    """Project response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    description: Optional[str] = None
    url: Optional[str] = None
    repo_url: Optional[str] = None
    technologies: List[str] = []
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    created_at: datetime


class CertificationCreateRequest(BaseModel):
    """Certification creation schema."""

    name: str = Field(min_length=1, max_length=200)
    issuer: str = Field(min_length=1, max_length=200)
    issue_date: Optional[date] = None
    expiration_date: Optional[date] = None
    credential_id: Optional[str] = None
    credential_url: Optional[str] = None


class CertificationResponse(BaseModel):
    """Certification response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    issuer: str
    issue_date: Optional[date] = None
    expiration_date: Optional[date] = None
    credential_id: Optional[str] = None
    credential_url: Optional[str] = None
    created_at: datetime


class FullCandidateProfileResponse(BaseModel):
    """Aggregated candidate profile response."""

    user_id: int
    email: str
    full_name: str
    profile: Optional[ProfileResponse] = None
    skills: List[SkillResponse] = []
    educations: List[EducationResponse] = []
    experiences: List[ExperienceResponse] = []
    projects: List[ProjectResponse] = []
    certifications: List[CertificationResponse] = []
