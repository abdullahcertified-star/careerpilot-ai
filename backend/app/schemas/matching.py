"""Pydantic schemas for deterministic job matching, ranking, and scoring."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.job import JobPostingResponse


class ComponentScores(BaseModel):
    """Detailed score breakdown per evaluation component (0.0 - 100.0)."""

    required_skills: float = Field(..., ge=0.0, le=100.0)
    role_relevance: float = Field(..., ge=0.0, le=100.0)
    experience_seniority: float = Field(..., ge=0.0, le=100.0)
    education_certifications: float = Field(..., ge=0.0, le=100.0)
    location_work_authorization: float = Field(..., ge=0.0, le=100.0)
    preferred_skills: float = Field(..., ge=0.0, le=100.0)


class MatchedSkillItem(BaseModel):
    """Candidate skill matched to job requirements."""

    skill: str
    proficiency: Optional[str] = "intermediate"
    years: Optional[float] = 1.0
    verified: bool = True
    is_preferred: bool = False


class JobMatchResponse(BaseModel):
    """Comprehensive explainable evaluation of job-candidate alignment."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    job_id: int
    total_score: float = Field(..., ge=0.0, le=100.0)
    component_scores: ComponentScores
    weights_used: Dict[str, float]
    matched_skills: List[Dict[str, Any]]
    missing_skills: List[str]
    missing_preferred_skills: List[str]
    explanation: str
    candidate_profile_version: int
    scoring_version: str
    is_stale: bool
    created_at: datetime
    updated_at: datetime
    job: Optional[JobPostingResponse] = None


class RankedMatchListResponse(BaseModel):
    """Paginated list of ranked job matches with sorting and filter state."""

    items: List[JobMatchResponse]
    total_count: int
    page: int
    page_size: int
    has_more: bool
    scoring_version: str
    profile_version: int


class MatchPreferencesUpdate(BaseModel):
    """Configurable candidate preferences affecting matching evaluation."""

    target_job_titles: Optional[List[str]] = None
    location: Optional[str] = None
    remote_preference: Optional[str] = None  # remote, hybrid, onsite, flexible
    work_authorization_status: Optional[str] = None  # authorized_without_sponsorship, us_citizen, requires_sponsorship, unknown


class ScoringWeightsResponse(BaseModel):
    """Current active scoring weights configuration."""

    scoring_version: str
    weights: Dict[str, float]
    description: str
