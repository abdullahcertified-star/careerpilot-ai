"""Typed schemas for Phase 7 application preparation, package review, and submission."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProposedFormAnswers(BaseModel):
    """Structured form answers proposed from candidate verified profile facts."""

    full_name: str = Field(description="Candidate legal name")
    email: str = Field(description="Candidate verified contact email")
    phone: str = Field(default="", description="Candidate contact phone")
    location: str = Field(default="", description="Current location or city/state")
    work_authorization: str = Field(
        default="Authorized to work in US without sponsorship",
        description="Candidate work authorization status",
    )
    requires_sponsorship: bool = Field(
        default=False,
        description="Whether future visa sponsorship is required",
    )
    notice_period: str = Field(
        default="2 weeks", description="Candidate availability / notice period"
    )
    linkedin_url: str | None = Field(default=None, description="LinkedIn profile URL")
    github_url: str | None = Field(default=None, description="GitHub URL")
    portfolio_url: str | None = Field(
        default=None, description="Personal portfolio or website URL"
    )
    target_salary: str | None = Field(
        default=None, description="Salary expectation or target"
    )
    custom_answers: dict[str, Any] = Field(
        default_factory=dict,
        description="Employer-specific questionnaire answers",
    )
    sensitive_fields_requiring_manual_input: list[str] = Field(
        default_factory=lambda: [
            "social_security_number",
            "background_check_consent",
            "live_mfa_token",
            "captcha_response",
        ],
        description="Sensitive answers never automated or guessed",
    )


class JobSummaryDetails(BaseModel):
    """Job and employer details included in the application review package."""

    id: int
    title: str
    company: str
    location: str | None = None
    work_mode: str = "unspecified"
    employment_type: str = "full_time"
    canonical_url: str
    source: str
    source_id: str
    description_snippet: str = ""

    model_config = ConfigDict(from_attributes=True)


class DocumentVersionSummary(BaseModel):
    """Summary of a selected resume or cover letter document version."""

    document_id: int
    version_id: int
    version_number: int
    doc_type: str
    title: str
    formatted_text: str
    structured_data: dict[str, Any] = Field(default_factory=dict)
    factual_confidence_score: float | None = None
    is_approved: bool = False

    model_config = ConfigDict(from_attributes=True)


class ProviderCapabilityInfo(BaseModel):
    """Assessment of target job provider API capabilities and credentials."""

    provider_id: str
    provider_name: str
    is_direct_api: bool
    supports_submission: bool
    requires_credentials: bool
    has_credentials: bool
    submission_method: str  # "automated_api" or "manual_handoff"
    handoff_reason: str | None = None
    notes: str = ""


class ApplicationPackage(BaseModel):
    """Complete application package assembled for human review before approval."""

    application_id: int
    user_id: int
    workflow_thread_id: str
    job: JobSummaryDetails
    original_application_url: str
    resume: DocumentVersionSummary | None = None
    cover_letter: DocumentVersionSummary | None = None
    form_answers: ProposedFormAnswers
    provider_capability: ProviderCapabilityInfo
    submission_method: str  # "automated_api" or "manual_handoff"
    package_hash: str
    approval_status: str  # "pending", "approved", "rejected", "invalidated"
    approval_notes: str | None = None
    approved_at: datetime | None = None
    approved_package_hash: str | None = None
    is_content_altered_since_approval: bool = False
    last_error: str | None = None

    model_config = ConfigDict(from_attributes=True)


class FormAnswersUpdateRequest(BaseModel):
    """Candidate modification to proposed form answers."""

    form_answers: ProposedFormAnswers


class DocumentSelectionUpdateRequest(BaseModel):
    """Candidate selection of active document versions for this application."""

    resume_version_id: int | None = None
    cover_letter_version_id: int | None = None


class ApplicationApprovalReviewRequest(BaseModel):
    """Explicit human approval decision bound to the exact package contents."""

    approved: bool
    notes: str | None = None
    expected_package_hash: str | None = None
    job_id: int | None = None


class ApplicationSubmitRequest(BaseModel):
    """Client request to submit an approved application or generate handoff."""

    submission_key: str = Field(
        description="Unique client idempotency/submission key preventing duplicate attempts"
    )
    target_job_id: int | None = Field(
        default=None,
        description="Must match application's job_id; approval for job A cannot authorize job B",
    )
    confirmed_package_hash: str | None = Field(
        default=None,
        description="Expected package hash to verify content was not modified",
    )


class LabeledAnswerItem(BaseModel):
    """User-friendly labeled answer formatted for manual application copy-paste."""

    field_key: str
    label: str
    value: str
    is_sensitive: bool = False
    help_text: str | None = None


class ManualHandoffPacket(BaseModel):
    """Rich manual handoff packet for unsupported providers or unauthenticated portals."""

    application_id: int
    job_title: str
    company: str
    original_application_url: str
    resume_document_id: int | None = None
    resume_version_id: int | None = None
    cover_letter_document_id: int | None = None
    cover_letter_version_id: int | None = None
    cover_letter_text: str | None = None
    labeled_answers: list[LabeledAnswerItem] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    generated_at: datetime


class SubmissionAttemptResponse(BaseModel):
    """Audit record response for an application submission attempt."""

    id: int
    application_id: int
    submission_key: str
    actor_id: str
    provider_id: str
    submission_method: str
    status: str
    receipt_reference: str | None = None
    response_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    blind_resubmission_prevented: bool = False
    started_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SubmissionResult(BaseModel):
    """Internal outcome of an application submission attempt."""

    status: str  # "submitted", "manual_handoff", "confirmation_pending", "failed"
    receipt_reference: str | None = None
    response_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    blind_resubmission_prevented: bool = False
    handoff_packet: ManualHandoffPacket | None = None
