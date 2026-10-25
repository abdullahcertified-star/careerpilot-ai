"""Typed graph state and API schemas for Phase 6 durable workflow."""

from datetime import datetime
from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class WorkflowState(TypedDict, total=False):
    """Explicit typed state for LangGraph workflow execution."""

    thread_id: str
    user_id: int
    application_id: int | None
    idempotency_key: str

    # Job discovery & normalization inputs
    raw_job_url: str | None
    provider_id: str | None
    source_id: str | None
    job_id: int | None
    job_data: dict[str, Any] | None
    is_duplicate: bool

    # Matching & Candidate facts
    match_score: float | None
    match_details: dict[str, Any] | None
    meets_threshold: bool

    # Document generation & Quality validation
    template_id: str
    custom_instructions: str | None
    resume_document_id: int | None
    resume_version_id: int | None
    cover_letter_document_id: int | None
    cover_letter_version_id: int | None
    quality_report: dict[str, Any] | None
    validation_passed: bool

    # Application Preparation & Approval
    application_payload: dict[str, Any] | None
    human_approved: bool | None
    approval_notes: str | None
    submission_mode: str  # "manual_handoff" or "automated_api"

    # Status, Retries & Auditing
    status: str
    tracking_metadata: dict[str, Any] | None
    retry_count: int
    max_retries: int
    last_error: str | None


class ApplicationStartRequest(BaseModel):
    """Request payload to initiate or resume a durable job application workflow."""

    job_id: int | None = Field(
        default=None, description="Existing job posting ID if already discovered"
    )
    job_url: str | None = Field(
        default=None, description="Target job listing URL to import and process"
    )
    provider_id: str | None = Field(
        default=None, description="Provider ID (e.g. 'greenhouse')"
    )
    source_id: str | None = Field(
        default=None, description="Provider-specific job ID"
    )
    template_id: str = Field(
        default="modern", description="Resume and letter design template"
    )
    custom_instructions: str | None = Field(
        default=None, description="Optional tailoring emphasis"
    )
    submission_mode: str = Field(
        default="manual_handoff", description="'manual_handoff' or 'automated_api'"
    )
    idempotency_key: str | None = Field(
        default=None, description="Unique client key preventing duplicate runs"
    )


class ApplicationApprovalRequest(BaseModel):
    """Request payload to approve or reject an application interrupted at human approval."""

    approved: bool = Field(
        description="True to approve application submission; False to reject"
    )
    notes: str | None = Field(
        default=None, description="Optional notes or feedback for revision"
    )


class WorkflowHistoryItem(BaseModel):
    """Step execution audit log in the workflow timeline."""

    id: int
    node_name: str
    status: str
    details: dict[str, Any]
    error_message: str | None = None
    attempt_number: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationResponse(BaseModel):
    """Durable job application record response."""

    id: int
    user_id: int
    job_id: int | None = None
    resume_document_id: int | None = None
    resume_version_id: int | None = None
    cover_letter_document_id: int | None = None
    cover_letter_version_id: int | None = None
    idempotency_key: str
    workflow_thread_id: str
    status: str
    approval_status: str
    approval_notes: str | None = None
    approved_at: datetime | None = None
    submission_mode: str
    application_payload: dict[str, Any] = Field(default_factory=dict)
    tracking_metadata: dict[str, Any] = Field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 3
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    # Associated summaries
    job_title: str | None = None
    job_company: str | None = None
    recent_logs: list[WorkflowHistoryItem] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
