"""Typed graph state and API schemas for Phase 6 durable workflow."""

from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict
from pydantic import BaseModel, ConfigDict, Field


class WorkflowState(TypedDict, total=False):
    """Explicit typed state for LangGraph workflow execution."""

    thread_id: str
    user_id: int
    application_id: Optional[int]
    idempotency_key: str

    # Job discovery & normalization inputs
    raw_job_url: Optional[str]
    provider_id: Optional[str]
    source_id: Optional[str]
    job_id: Optional[int]
    job_data: Optional[Dict[str, Any]]
    is_duplicate: bool

    # Matching & Candidate facts
    match_score: Optional[float]
    match_details: Optional[Dict[str, Any]]
    meets_threshold: bool

    # Document generation & Quality validation
    template_id: str
    custom_instructions: Optional[str]
    resume_document_id: Optional[int]
    resume_version_id: Optional[int]
    cover_letter_document_id: Optional[int]
    cover_letter_version_id: Optional[int]
    quality_report: Optional[Dict[str, Any]]
    validation_passed: bool

    # Application Preparation & Approval
    application_payload: Optional[Dict[str, Any]]
    human_approved: Optional[bool]
    approval_notes: Optional[str]
    submission_mode: str  # "manual_handoff" or "automated_api"

    # Status, Retries & Auditing
    status: str
    tracking_metadata: Optional[Dict[str, Any]]
    retry_count: int
    max_retries: int
    last_error: Optional[str]


class ApplicationStartRequest(BaseModel):
    """Request payload to initiate or resume a durable job application workflow."""

    job_id: Optional[int] = Field(default=None, description="Existing job posting ID if already discovered")
    job_url: Optional[str] = Field(default=None, description="Target job listing URL to import and process")
    provider_id: Optional[str] = Field(default=None, description="Provider ID (e.g. 'greenhouse')")
    source_id: Optional[str] = Field(default=None, description="Provider-specific job ID")
    template_id: str = Field(default="modern", description="Resume and letter design template")
    custom_instructions: Optional[str] = Field(default=None, description="Optional tailoring emphasis")
    submission_mode: str = Field(default="manual_handoff", description="'manual_handoff' or 'automated_api'")
    idempotency_key: Optional[str] = Field(default=None, description="Unique client key preventing duplicate runs")


class ApplicationApprovalRequest(BaseModel):
    """Request payload to approve or reject an application interrupted at human approval."""

    approved: bool = Field(description="True to approve application submission; False to reject")
    notes: Optional[str] = Field(default=None, description="Optional notes or feedback for revision")


class WorkflowHistoryItem(BaseModel):
    """Step execution audit log in the workflow timeline."""

    id: int
    node_name: str
    status: str
    details: Dict[str, Any]
    error_message: Optional[str] = None
    attempt_number: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationResponse(BaseModel):
    """Durable job application record response."""

    id: int
    user_id: int
    job_id: Optional[int] = None
    resume_document_id: Optional[int] = None
    resume_version_id: Optional[int] = None
    cover_letter_document_id: Optional[int] = None
    cover_letter_version_id: Optional[int] = None
    idempotency_key: str
    workflow_thread_id: str
    status: str
    approval_status: str
    approval_notes: Optional[str] = None
    approved_at: Optional[datetime] = None
    submission_mode: str
    application_payload: Dict[str, Any] = Field(default_factory=dict)
    tracking_metadata: Dict[str, Any] = Field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 3
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Associated summaries
    job_title: Optional[str] = None
    job_company: Optional[str] = None
    recent_logs: List[WorkflowHistoryItem] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
