"""Structured schemas for resume and cover letter generation, factual verification, and document versions."""

from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ResumeExperienceItem(BaseModel):
    """Structured experience entry in tailored resume."""

    company: str = Field(description="Company or organization name")
    title: str = Field(description="Exact candidate job title held")
    start_date: str = Field(description="Employment start date/year")
    end_date: str = Field(description="Employment end date/year or 'Present'")
    is_current: bool = Field(default=False, description="Whether this is the candidate's current role")
    location: Optional[str] = Field(default=None, description="Location of work")
    bullets: List[str] = Field(
        default_factory=list,
        description="Factual responsibility and achievement bullets grounded strictly in verified experience",
    )


class ResumeEducationItem(BaseModel):
    """Structured education entry in tailored resume."""

    institution: str = Field(description="Name of university or institution")
    degree: str = Field(description="Degree name, e.g., Bachelor of Science")
    field_of_study: str = Field(description="Field of study or major")
    graduation_year: Optional[str] = Field(default=None, description="Graduation year or dates attended")


class ResumeProjectItem(BaseModel):
    """Structured project entry in tailored resume."""

    name: str = Field(description="Name of the authentic candidate project")
    description: str = Field(description="Summary of project architecture and achievements")
    technologies: List[str] = Field(default_factory=list, description="List of verified technologies used")
    url: Optional[str] = Field(default=None, description="Repository or project URL")


class ResumeCertificationItem(BaseModel):
    """Structured certification entry in tailored resume."""

    name: str = Field(description="Name of earned credential or certification")
    issuer: str = Field(description="Issuing organization")
    issue_year: Optional[str] = Field(default=None, description="Year credential was awarded")


class StructuredResume(BaseModel):
    """Structured schema for LLM-tailored resume output."""

    full_name: str = Field(description="Candidate full name")
    email: str = Field(description="Candidate email address")
    phone: Optional[str] = Field(default=None, description="Candidate contact number")
    location: Optional[str] = Field(default=None, description="Candidate location")
    linkedin_url: Optional[str] = Field(default=None, description="LinkedIn profile URL")
    github_url: Optional[str] = Field(default=None, description="GitHub profile URL")
    target_title: str = Field(description="Target role title matching job posting")
    target_company: str = Field(description="Target employer name")
    professional_summary: str = Field(description="Tailored summary highlighting relevant verified background")
    highlighted_skills: List[str] = Field(
        default_factory=list,
        description="Key technical and domain skills relevant to requisition that candidate possesses",
    )
    experience: List[ResumeExperienceItem] = Field(
        default_factory=list,
        description="Factual work experience items strictly matching verified employment history",
    )
    projects: List[ResumeProjectItem] = Field(
        default_factory=list,
        description="Authentic candidate projects matching job relevance",
    )
    education: List[ResumeEducationItem] = Field(
        default_factory=list,
        description="Academic degrees and qualifications",
    )
    certifications: List[ResumeCertificationItem] = Field(
        default_factory=list,
        description="Verified certifications and credentials",
    )


class StructuredCoverLetter(BaseModel):
    """Structured schema for LLM-tailored cover letter output."""

    sender_name: str = Field(description="Candidate full name")
    sender_email: str = Field(description="Candidate email address")
    sender_phone: Optional[str] = Field(default=None, description="Candidate phone number")
    sender_location: Optional[str] = Field(default=None, description="Candidate location")
    target_company: str = Field(description="Hiring company or organization")
    target_title: str = Field(description="Exact position title applied for")
    salutation: str = Field(default="Dear Hiring Team,", description="Formal letter salutation")
    opening_paragraph: str = Field(description="Compelling opening stating role and genuine motivation")
    body_paragraphs: List[str] = Field(
        default_factory=list,
        description="Body paragraphs connecting candidate genuine experience and skills to the company's needs",
    )
    closing_paragraph: str = Field(description="Closing paragraph summarizing genuine value and availability")
    call_to_action: str = Field(description="Polite request for discussion or interview")
    sign_off: str = Field(default="Sincerely,", description="Formal letter sign-off")


class UnsupportedClaim(BaseModel):
    """Detail on a flagged claim that lacks verification in candidate profile."""

    field: str = Field(description="Field where claim was found (e.g. 'experience', 'skill', 'education')")
    claim: str = Field(description="Text or entity claimed in document")
    reason: str = Field(description="Why claim is considered unsupported or conflicting")
    severity: str = Field(default="error", description="'error' for ungrounded facts, 'warning' for minor discrepancies")
    line_or_context: Optional[str] = Field(default=None, description="Context snippet where claim appeared")


class FactualValidationReport(BaseModel):
    """Audit report produced by the automated factual consistency checker."""

    is_clean: bool = Field(description="Whether document contains zero ungrounded or fabricated claims")
    factual_confidence_score: float = Field(
        ge=0.0, le=100.0, description="Confidence score from 0 to 100 based on verified fact ratio"
    )
    total_claims_checked: int = Field(default=0, description="Total facts and entities verified")
    verified_claims_count: int = Field(default=0, description="Count of claims confirmed in candidate profile")
    unsupported_claims: List[UnsupportedClaim] = Field(default_factory=list, description="Flagged unsupported claims")
    verified_facts: List[str] = Field(default_factory=list, description="Summary of confirmed facts")
    warnings: List[str] = Field(default_factory=list, description="Advisory consistency notes")


class DocumentGenerateRequest(BaseModel):
    """Request payload to generate a tailored resume or cover letter."""

    job_id: int = Field(description="Target job posting ID")
    doc_type: str = Field(default="resume", description="'resume' or 'cover_letter'")
    template_id: str = Field(default="modern", description="Visual template: 'modern', 'classic', 'technical', 'executive'")
    custom_instructions: Optional[str] = Field(default=None, description="Optional user preferences or emphasis")


class DocumentUpdateRequest(BaseModel):
    """Request payload to edit structured document and create a new version."""

    structured_data: dict[str, Any] = Field(description="Updated structured resume or cover letter data")
    template_id: Optional[str] = Field(default=None, description="Updated template ID")
    change_summary: str = Field(default="User manual edit", description="Summary of changes made")
    is_approved: Optional[bool] = Field(default=None, description="Whether user approves this version")


class DocumentVersionResponse(BaseModel):
    """Response representing an immutable document revision."""

    id: int
    document_id: int
    version_number: int
    structured_data: dict[str, Any]
    formatted_text: str
    model_name: str
    prompt_version: str
    validation_report: FactualValidationReport
    is_approved: bool
    change_summary: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GeneratedDocumentResponse(BaseModel):
    """Response representing a generated document container with its latest version."""

    id: int
    user_id: int
    job_id: int
    doc_type: str
    title: str
    template_id: str
    candidate_profile_version: int
    created_at: datetime
    updated_at: datetime
    latest_version: Optional[DocumentVersionResponse] = None
    versions_count: int = 1
    job_title: Optional[str] = None
    job_company: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
