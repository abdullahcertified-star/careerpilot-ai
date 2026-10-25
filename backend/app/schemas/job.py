from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ProviderCapabilities(BaseModel):
    """Capabilities and metadata exposed by a job provider adapter."""

    provider_id: str
    name: str
    description: str
    integration_status: str  # verified_live_api, link_first, verified_secure_import, planned
    supports_search: bool = True
    supports_details: bool = True
    supports_url_import: bool = False
    is_direct_api: bool = False
    link_first_only: bool = False
    rate_limit_rpm: int = 60
    documentation_url: Optional[str] = None
    external_search_template: Optional[str] = None


class JobSearchQuery(BaseModel):
    """Normalized search query parameters across providers."""

    query: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[str] = None  # remote, hybrid, onsite
    provider_id: Optional[str] = None  # greenhouse, all, etc.
    board_token: Optional[str] = None  # greenhouse specific board token e.g. gitlab, cloudflare
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class NormalizedJob(BaseModel):
    """Canonical representation of a discovered or imported job posting."""

    source: str
    source_id: str
    canonical_url: str
    title: str
    company: str
    description: str
    location: Optional[str] = None
    work_mode: str = "unspecified"  # remote, hybrid, onsite, unspecified
    employment_type: str = "full_time"  # full_time, part_time, contract, internship, other
    department: Optional[str] = None
    posted_at: Optional[datetime] = None
    retrieved_at: datetime
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class JobSearchResult(BaseModel):
    """Paginated search response with provider status and attribution."""

    jobs: List[NormalizedJob] = Field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 20
    has_more: bool = False
    provider_id: str
    provider_status: str
    warnings: List[str] = Field(default_factory=list)
    external_search_url: Optional[str] = None


class JobPostingResponse(BaseModel):
    """Response model for a persisted job posting."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    source_id: str
    canonical_url: str
    title: str
    company: str
    description: str
    location: Optional[str] = None
    work_mode: str
    employment_type: str
    department: Optional[str] = None
    posted_at: Optional[datetime] = None
    retrieved_at: datetime
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool
    is_saved: bool = False
    saved_id: Optional[int] = None
    saved_status: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SavedJobResponse(BaseModel):
    """Response model for a candidate's saved job bookmark."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    job_id: int
    status: str  # saved, applied, interviewing, offered, rejected
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    job: JobPostingResponse


class SavedJobCreate(BaseModel):
    """Payload to save/bookmark a job posting."""

    notes: Optional[str] = None
    status: str = "saved"


class SavedJobUpdate(BaseModel):
    """Payload to update saved job notes or candidate status."""

    status: Optional[str] = None
    notes: Optional[str] = None


class JobImportRequest(BaseModel):
    """Payload for manual job URL import."""

    url: str
