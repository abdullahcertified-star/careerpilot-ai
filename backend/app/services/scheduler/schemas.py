"""Typed schemas for Phase 8 scheduled job discovery, saved searches, and notifications."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field


class SavedSearchCreate(BaseModel):
    """Client request to create a new user-configured saved search."""

    name: str = Field(
        min_length=1, max_length=150, description="Friendly name for the search"
    )
    role: str | None = Field(
        default=None, max_length=150, description="Target job title or role"
    )
    keywords: list[str] = Field(
        default_factory=list, description="Target skills or keywords"
    )
    location: str | None = Field(
        default=None, max_length=150, description="City, state, or geographic area"
    )
    work_mode: str = Field(default="any", description="remote, hybrid, onsite, or any")
    employment_type: str = Field(
        default="any", description="full_time, contract, internship, or any"
    )
    min_match_score: float = Field(
        default=70.0,
        ge=0.0,
        le=100.0,
        description="Minimum match score required to trigger notifications",
    )
    interval_minutes: int = Field(
        default=60,
        ge=15,
        le=10080,
        description="Scan interval in minutes (min 15 mins)",
    )
    provider_id: str = Field(default="all", description="Target provider ID or 'all'")
    in_app_notifications: bool = Field(
        default=True, description="Enable in-app notifications for high-match jobs"
    )
    email_notifications: bool = Field(
        default=False,
        description="Enable email notifications (requires consent and SMTP config)",
    )


class SavedSearchUpdate(BaseModel):
    """Client request to update an existing saved search."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    role: str | None = Field(default=None, max_length=150)
    keywords: list[str] | None = None
    location: str | None = Field(default=None, max_length=150)
    work_mode: str | None = None
    employment_type: str | None = None
    min_match_score: float | None = Field(default=None, ge=0.0, le=100.0)
    interval_minutes: int | None = Field(default=None, ge=15, le=10080)
    provider_id: str | None = None
    in_app_notifications: bool | None = None
    email_notifications: bool | None = None


class ScheduledScanRunResponse(BaseModel):
    """Response representing an individual scan execution."""

    id: int
    saved_search_id: int
    status: str
    idempotency_key: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
    jobs_found: int = 0
    new_jobs_ingested: int = 0
    high_matches_found: int = 0
    error_message: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    run_metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class SavedSearchResponse(BaseModel):
    """Complete representation of a saved search with operational metrics."""

    id: int
    user_id: int
    name: str
    role: str | None = None
    keywords: list[str] = Field(default_factory=list)
    location: str | None = None
    work_mode: str
    employment_type: str
    min_match_score: float
    interval_minutes: int
    provider_id: str
    is_active: bool
    in_app_notifications: bool
    email_notifications: bool
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    next_run_at: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    total_runs_count: int = 0
    created_at: datetime
    updated_at: datetime
    latest_run: ScheduledScanRunResponse | None = None

    @computed_field
    @property
    def is_paused(self) -> bool:
        return not self.is_active

    @computed_field
    @property
    def total_runs(self) -> int:
        return self.total_runs_count

    model_config = ConfigDict(from_attributes=True)


class SavedSearchListResponse(BaseModel):
    """List of saved searches for candidate."""

    items: list[SavedSearchResponse]
    total_count: int
    active_count: int
    paused_count: int


class ScanCancelResponse(BaseModel):
    """Response confirming cancellation of an ongoing scan."""

    saved_search_id: int
    status: str
    message: str


class NotificationResponse(BaseModel):
    """In-app notification payload."""

    id: int
    user_id: int
    type: str  # high_match_job, pending_approval_reminder, scan_failure_alert, system
    title: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    is_read: bool
    read_at: datetime | None = None
    email_sent: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    """Paginated notifications response."""

    items: list[NotificationResponse]
    total_count: int
    unread_count: int


class NotificationUnreadCountResponse(BaseModel):
    """Quick badge count of unread notifications."""

    unread_count: int
