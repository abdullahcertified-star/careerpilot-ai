from datetime import date
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class EvidenceSource(BaseModel):
    """Source reference and verbatim quote grounding an extracted fact."""

    text_snippet: str = Field(description="Exact snippet from resume providing evidence for this fact")
    page_number: Optional[int] = Field(default=1, description="Page index where evidence appears")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="Extraction confidence score")


class ExtractedSkill(BaseModel):
    name: str
    category: str = "technical"
    proficiency_level: str = "intermediate"
    years_experience: float = 1.0
    evidence: EvidenceSource
    is_confirmed: bool = True  # User can toggle off


class ExtractedEducation(BaseModel):
    institution: str
    degree: str
    field_of_study: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[str] = None
    evidence: EvidenceSource
    is_confirmed: bool = True


class ExtractedExperience(BaseModel):
    company: str
    title: str
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False
    description: Optional[str] = None
    achievements: List[str] = []
    evidence: EvidenceSource
    is_confirmed: bool = True


class ExtractedProject(BaseModel):
    title: str
    description: Optional[str] = None
    url: Optional[str] = None
    repo_url: Optional[str] = None
    technologies: List[str] = []
    evidence: EvidenceSource
    is_confirmed: bool = True


class ExtractedCertification(BaseModel):
    name: str
    issuer: str
    issue_date: Optional[str] = None
    expiration_date: Optional[str] = None
    credential_id: Optional[str] = None
    evidence: EvidenceSource
    is_confirmed: bool = True


class ExtractedProfileData(BaseModel):
    """Staged candidate extraction payload separate from verified profile."""

    model_config = ConfigDict(from_attributes=True)

    headline: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    skills: List[ExtractedSkill] = []
    education: List[ExtractedEducation] = []
    experience: List[ExtractedExperience] = []
    projects: List[ExtractedProject] = []
    certifications: List[ExtractedCertification] = []


class ResumeExtractionResponse(BaseModel):
    """Response schema for a resume extraction."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    resume_id: int
    user_id: int
    status: str
    page_count: int
    extracted_data: ExtractedProfileData


class ResumeConfirmRequest(BaseModel):
    """Payload to confirm and merge staged facts into candidate profile."""

    data: ExtractedProfileData
    override_headline: bool = True
    override_bio: bool = True
    override_location: bool = True
