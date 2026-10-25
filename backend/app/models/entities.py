from datetime import UTC, date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(UTC)


class User(Base):
    """User account model."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="candidate", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    # Relationships
    profile: Mapped[Optional["Profile"]] = relationship(
        "Profile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    skills: Mapped[list["Skill"]] = relationship(
        "Skill", back_populates="user", cascade="all, delete-orphan"
    )
    educations: Mapped[list["Education"]] = relationship(
        "Education", back_populates="user", cascade="all, delete-orphan"
    )
    experiences: Mapped[list["Experience"]] = relationship(
        "Experience", back_populates="user", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(
        "Project", back_populates="user", cascade="all, delete-orphan"
    )
    certifications: Mapped[list["Certification"]] = relationship(
        "Certification", back_populates="user", cascade="all, delete-orphan"
    )
    resumes: Mapped[list["ResumeMetadata"]] = relationship(
        "ResumeMetadata", back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    saved_jobs: Mapped[list["SavedJob"]] = relationship(
        "SavedJob", back_populates="user", cascade="all, delete-orphan"
    )
    matches: Mapped[list["JobMatch"]] = relationship(
        "JobMatch", back_populates="user", cascade="all, delete-orphan"
    )
    generated_documents: Mapped[list["GeneratedDocument"]] = relationship(
        "GeneratedDocument", back_populates="user", cascade="all, delete-orphan"
    )
    applications: Mapped[list["JobApplication"]] = relationship(
        "JobApplication", back_populates="user", cascade="all, delete-orphan"
    )
    submission_attempts: Mapped[list["ApplicationSubmissionAttempt"]] = relationship(
        "ApplicationSubmissionAttempt",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    saved_searches: Mapped[list["SavedSearch"]] = relationship(
        "SavedSearch",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(SavedSearch.created_at)",
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(Notification.created_at)",
    )


class Profile(Base):
    """Candidate profile model with career preferences."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    headline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_job_titles: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    target_salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remote_preference: Mapped[str] = mapped_column(
        String(50), default="flexible", nullable=False
    )
    work_authorization_status: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    profile_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="profile")


class Skill(Base):
    """Candidate skills with category and proficiency level."""

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str] = mapped_column(
        String(50), default="technical", nullable=False
    )
    proficiency_level: Mapped[str] = mapped_column(
        String(50), default="intermediate", nullable=False
    )
    years_experience: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="skills")


class Education(Base):
    """Academic history model."""

    __tablename__ = "educations"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    institution: Mapped[str] = mapped_column(String(255), nullable=False)
    degree: Mapped[str] = mapped_column(String(100), nullable=False)
    field_of_study: Mapped[str] = mapped_column(String(150), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gpa: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="educations")


class Experience(Base):
    """Employment and professional experience model."""

    __tablename__ = "experiences"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    achievements: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="experiences")


class Project(Base):
    """Portfolio project model."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    repo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    technologies: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="projects")


class Certification(Base):
    """Professional certification and licensing model."""

    __tablename__ = "certifications"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer: Mapped[str] = mapped_column(String(200), nullable=False)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    credential_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    credential_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="certifications")


class ResumeMetadata(Base):
    """Resume file metadata and parsing result."""

    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(100), default="application/pdf", nullable=False
    )
    parsed_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="resumes")
    extraction: Mapped[Optional["ResumeExtraction"]] = relationship(
        "ResumeExtraction",
        back_populates="resume",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ResumeExtraction(Base):
    """Staged extracted facts from resume with source evidence, kept separate from verified profile."""

    __tablename__ = "resume_extractions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    resume_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("resumes.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), default="pending_review", nullable=False
    )  # pending_review, confirmed, rejected
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_data: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    page_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    resume: Mapped["ResumeMetadata"] = relationship(
        "ResumeMetadata", back_populates="extraction"
    )
    user: Mapped["User"] = relationship("User")


class ProfileChangeLog(Base):
    """Audit log tracking changes made to verified candidate profile."""

    __tablename__ = "profile_change_logs"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(
        String(100), default="manual_edit", nullable=False
    )
    changes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User")


class UserSession(Base):
    """Server-managed user authentication sessions."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="sessions")


class JobPosting(Base):
    """Normalized job posting discovered from providers or manually imported."""

    __tablename__ = "job_postings"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # greenhouse, manual_import, linkedin, indeed
    source_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    canonical_url: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_mode: Mapped[str] = mapped_column(
        String(50), default="unspecified", nullable=False
    )  # remote, hybrid, onsite, unspecified
    employment_type: Mapped[str] = mapped_column(
        String(50), default="full_time", nullable=False
    )  # full_time, part_time, contract, internship, other
    department: Mapped[str | None] = mapped_column(String(150), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "source", "source_id", name="uq_job_postings_source_source_id"
        ),
    )

    saved_by_users: Mapped[list["SavedJob"]] = relationship(
        "SavedJob", back_populates="job", cascade="all, delete-orphan"
    )
    matches: Mapped[list["JobMatch"]] = relationship(
        "JobMatch", back_populates="job", cascade="all, delete-orphan"
    )
    generated_documents: Mapped[list["GeneratedDocument"]] = relationship(
        "GeneratedDocument", back_populates="job", cascade="all, delete-orphan"
    )
    applications: Mapped[list["JobApplication"]] = relationship(
        "JobApplication", back_populates="job"
    )


class SavedJob(Base):
    """User bookmarked/saved job tracking status and candidate notes."""

    __tablename__ = "saved_jobs"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("job_postings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50), default="saved", nullable=False
    )  # saved, applied, interviewing, offered, rejected
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_saved_jobs_user_id_job_id"),
    )

    user: Mapped["User"] = relationship("User", back_populates="saved_jobs")
    job: Mapped["JobPosting"] = relationship(
        "JobPosting", back_populates="saved_by_users"
    )


class JobMatch(Base):
    """Deterministic match evaluation between candidate profile and a job posting."""

    __tablename__ = "job_matches"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("job_postings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    total_score: Mapped[float] = mapped_column(
        Float, nullable=False, index=True
    )  # 0.0 - 100.0
    component_scores: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    matched_skills: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    missing_skills: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    missing_preferred_skills: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_profile_version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    scoring_version: Mapped[str] = mapped_column(
        String(20), default="1.0.0", nullable=False
    )
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_job_matches_user_id_job_id"),
    )

    user: Mapped["User"] = relationship("User", back_populates="matches")
    job: Mapped["JobPosting"] = relationship("JobPosting", back_populates="matches")


class GeneratedDocument(Base):
    """Job-specific generated resume or cover letter document container."""

    __tablename__ = "generated_documents"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("job_postings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doc_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # "resume" or "cover_letter"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    template_id: Mapped[str] = mapped_column(
        String(50), default="modern", nullable=False
    )
    candidate_profile_version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="generated_documents")
    job: Mapped["JobPosting"] = relationship(
        "JobPosting", back_populates="generated_documents"
    )
    versions: Mapped[list["DocumentVersion"]] = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="desc(DocumentVersion.version_number)",
    )


class DocumentVersion(Base):
    """Immutable version of a generated document with audit trail and validation report."""

    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("generated_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    structured_data: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    formatted_text: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(
        String(100), default="mock-agent-v1", nullable=False
    )
    prompt_version: Mapped[str] = mapped_column(
        String(30), default="1.0.0", nullable=False
    )
    validation_report: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    change_summary: Mapped[str] = mapped_column(
        String(255), default="Generated version", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_number", name="uq_doc_versions_doc_id_version_num"
        ),
    )

    document: Mapped["GeneratedDocument"] = relationship(
        "GeneratedDocument", back_populates="versions"
    )


class JobApplication(Base):
    """Durable record of a candidate job application and its workflow progress."""

    __tablename__ = "job_applications"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("job_postings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resume_document_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("generated_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    resume_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True
    )
    cover_letter_document_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("generated_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    cover_letter_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    workflow_thread_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(64), default="pending", nullable=False, index=True
    )
    approval_status: Mapped[str] = mapped_column(
        String(64), default="pending", nullable=False, index=True
    )  # pending, approved, rejected, invalidated
    approval_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submission_mode: Mapped[str] = mapped_column(
        String(64), default="manual_handoff", nullable=False
    )  # manual_handoff, automated_api
    application_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    form_answers: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    approval_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    approved_package_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    tracking_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="applications")
    job: Mapped[Optional["JobPosting"]] = relationship(
        "JobPosting", back_populates="applications"
    )
    execution_logs: Mapped[list["WorkflowExecutionLog"]] = relationship(
        "WorkflowExecutionLog",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="desc(WorkflowExecutionLog.created_at)",
    )
    submission_attempts: Mapped[list["ApplicationSubmissionAttempt"]] = relationship(
        "ApplicationSubmissionAttempt",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="desc(ApplicationSubmissionAttempt.started_at)",
    )


class WorkflowExecutionLog(Base):
    """Detailed audit log of state transitions and node executions in the workflow."""

    __tablename__ = "workflow_execution_logs"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("job_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    node_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # started, completed, failed, interrupted
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    application: Mapped["JobApplication"] = relationship(
        "JobApplication", back_populates="execution_logs"
    )


class ApplicationSubmissionAttempt(Base):
    """Immutable audit record of an application submission attempt or manual handoff."""

    __tablename__ = "application_submission_attempts"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("job_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submission_key: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    actor_id: Mapped[str] = mapped_column(
        String(100), default="candidate", nullable=False
    )
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    submission_method: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # "automated_api" or "manual_handoff"
    status: Mapped[str] = mapped_column(
        String(64), default="started", nullable=False, index=True
    )  # "submitted", "manual_handoff", "confirmation_pending", "failed"
    package_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    resume_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cover_letter_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    form_answers_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    receipt_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    response_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    blind_resubmission_prevented: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "submission_key", name="uq_submission_attempts_submission_key"
        ),
    )

    application: Mapped["JobApplication"] = relationship(
        "JobApplication", back_populates="submission_attempts"
    )
    user: Mapped["User"] = relationship("User", back_populates="submission_attempts")


class SavedSearch(Base):
    """User-configured scheduled job search with criteria, frequency, and execution state."""

    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[str | None] = mapped_column(String(150), nullable=True)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    work_mode: Mapped[str] = mapped_column(
        String(50), default="any", nullable=False
    )  # any, remote, hybrid, onsite
    employment_type: Mapped[str] = mapped_column(
        String(50), default="any", nullable=False
    )  # any, full_time, contract, internship, other
    min_match_score: Mapped[float] = mapped_column(
        Float, default=70.0, nullable=False
    )  # 0.0 - 100.0
    interval_minutes: Mapped[int] = mapped_column(
        Integer, default=60, nullable=False
    )  # default 60 mins (hourly)
    provider_id: Mapped[str] = mapped_column(
        String(50), default="all", nullable=False
    )  # all, greenhouse, etc.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )  # True = running, False = paused
    in_app_notifications: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    email_notifications: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    total_runs_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="saved_searches")
    scan_runs: Mapped[list["ScheduledScanRun"]] = relationship(
        "ScheduledScanRun",
        back_populates="saved_search",
        cascade="all, delete-orphan",
        order_by="desc(ScheduledScanRun.started_at)",
        lazy="selectin",
    )

    @property
    def is_paused(self) -> bool:
        return not self.is_active

    @is_paused.setter
    def is_paused(self, value: bool) -> None:
        self.is_active = not value

    @property
    def total_runs(self) -> int:
        return self.total_runs_count

    @total_runs.setter
    def total_runs(self, value: int) -> None:
        self.total_runs_count = value


class ScheduledScanRun(Base):
    """Execution record and operational metrics for an individual scheduled scan run."""

    __tablename__ = "scheduled_scan_runs"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    saved_search_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("saved_searches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False, index=True
    )  # pending, running, completed, failed, cancelled
    idempotency_key: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_jobs_ingested: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    high_matches_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    run_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )

    saved_search: Mapped["SavedSearch"] = relationship(
        "SavedSearch", back_populates="scan_runs"
    )


class Notification(Base):
    """User notifications for new high-match job opportunities and review reminders."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # high_match_job, pending_approval_reminder, scan_failure_alert, system
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    user: Mapped["User"] = relationship("User", back_populates="notifications")
