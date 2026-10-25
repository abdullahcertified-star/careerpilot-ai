"""Submission orchestration service for Phase 7 review-first application lifecycle."""

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import (
    ApplicationSubmissionAttempt,
    DocumentVersion,
    JobApplication,
    JobPosting,
    Profile,
    User,
    WorkflowExecutionLog,
)
from app.services.submission.adapters.registry import submission_registry
from app.services.submission.schemas import (
    ApplicationApprovalReviewRequest,
    ApplicationPackage,
    ApplicationSubmitRequest,
    DocumentVersionSummary,
    JobSummaryDetails,
    ProposedFormAnswers,
    SubmissionAttemptResponse,
    SubmissionResult,
)
from app.services.workflow.nodes import UnauthorizedSubmissionError
from app.services.workflow.redactor import redact_sensitive_value

logger = logging.getLogger(__name__)


class DuplicateSubmissionError(Exception):
    """Raised when duplicate submission key is submitted simultaneously."""


class BlindResubmissionError(Exception):
    """Raised when submission is attempted while previous attempt outcome is pending confirmation."""


def compute_package_hash(
    job_id: int,
    canonical_url: str,
    resume_version_id: int | None,
    cover_letter_version_id: int | None,
    form_answers: dict[str, Any],
    submission_method: str,
) -> str:
    """Compute deterministic SHA-256 fingerprint of the complete application review package."""
    payload = {
        "job_id": job_id,
        "canonical_url": canonical_url,
        "resume_version_id": resume_version_id,
        "cover_letter_version_id": cover_letter_version_id,
        "form_answers": form_answers,
        "submission_method": submission_method,
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SubmissionService:
    """Service managing secure package preparation, candidate review, approval gates, and permitted submission."""

    async def prepare_package(
        self,
        session: AsyncSession,
        user_id: int,
        application_id: int,
    ) -> ApplicationPackage:
        """Assemble or reload the complete application review package."""
        stmt = (
            select(JobApplication)
            .options(
                selectinload(JobApplication.job),
                selectinload(JobApplication.execution_logs),
                selectinload(JobApplication.submission_attempts),
            )
            .where(
                JobApplication.id == application_id,
                JobApplication.user_id == user_id,
            )
        )
        app = (await session.execute(stmt)).scalar_one_or_none()
        if not app:
            raise ValueError(f"Application {application_id} not found or access denied")

        # Load candidate user and verified profile facts
        user_stmt = (
            select(User)
            .options(
                selectinload(User.profile),
                selectinload(User.skills),
                selectinload(User.experiences),
            )
            .where(User.id == user_id)
        )
        user = (await session.execute(user_stmt)).scalar_one_or_none()
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Load job posting
        job = app.job
        if not job and app.job_id:
            job_stmt = select(JobPosting).where(JobPosting.id == app.job_id)
            job = (await session.execute(job_stmt)).scalar_one_or_none()

        if not job:
            raise ValueError("Application has no associated job posting")

        # 1. Propose structured form answers from profile facts
        profile: Profile | None = user.profile
        existing_answers = app.form_answers or {}
        if not existing_answers:
            answers = ProposedFormAnswers(
                full_name=user.full_name,
                email=user.email,
                phone=profile.phone or "" if profile else "",
                location=profile.location or "" if profile else "",
                work_authorization=(
                    profile.work_authorization_status
                    if profile and profile.work_authorization_status
                    else "Authorized to work in US without sponsorship"
                ),
                requires_sponsorship=False,
                notice_period="2 weeks",
                linkedin_url=profile.linkedin_url if profile else None,
                github_url=profile.github_url if profile else None,
                portfolio_url=profile.website_url if profile else None,
                target_salary=str(profile.target_salary_min)
                if profile and profile.target_salary_min
                else None,
            )
            app.form_answers = answers.model_dump()
        else:
            answers = ProposedFormAnswers(**existing_answers)

        # 2. Load active resume version
        resume_summary: DocumentVersionSummary | None = None
        if app.resume_version_id:
            v_stmt = select(DocumentVersion).where(
                DocumentVersion.id == app.resume_version_id
            )
            v = (await session.execute(v_stmt)).scalar_one_or_none()
            if v:
                resume_summary = DocumentVersionSummary(
                    document_id=v.document_id,
                    version_id=v.id,
                    version_number=v.version_number,
                    doc_type="resume",
                    title="Tailored Resume",
                    formatted_text=v.formatted_text,
                    structured_data=v.structured_data,
                    factual_confidence_score=(
                        v.validation_report.get("factual_confidence_score")
                        if isinstance(v.validation_report, dict)
                        else None
                    ),
                    is_approved=v.is_approved,
                )

        # 3. Load active cover letter version
        cover_summary: DocumentVersionSummary | None = None
        if app.cover_letter_version_id:
            cv_stmt = select(DocumentVersion).where(
                DocumentVersion.id == app.cover_letter_version_id
            )
            cv = (await session.execute(cv_stmt)).scalar_one_or_none()
            if cv:
                cover_summary = DocumentVersionSummary(
                    document_id=cv.document_id,
                    version_id=cv.id,
                    version_number=cv.version_number,
                    doc_type="cover_letter",
                    title="Tailored Cover Letter",
                    formatted_text=cv.formatted_text,
                    structured_data=cv.structured_data,
                    is_approved=cv.is_approved,
                )

        # 4. Determine provider capability
        provider_cap = submission_registry.get_capability(job.source, {})
        submission_method = provider_cap.submission_method

        # 5. Compute package hash
        current_hash = compute_package_hash(
            job_id=job.id,
            canonical_url=job.canonical_url,
            resume_version_id=app.resume_version_id,
            cover_letter_version_id=app.cover_letter_version_id,
            form_answers=answers.model_dump(),
            submission_method=submission_method,
        )

        is_altered = bool(
            app.approved_package_hash and app.approved_package_hash != current_hash
        )

        # Synchronize application payload in DB
        app.submission_mode = submission_method
        await session.commit()
        await session.refresh(app)

        job_details = JobSummaryDetails(
            id=job.id,
            title=job.title,
            company=job.company,
            location=job.location,
            work_mode=job.work_mode,
            employment_type=job.employment_type,
            canonical_url=job.canonical_url,
            source=job.source,
            source_id=job.source_id,
            description_snippet=job.description[:250] + "..."
            if len(job.description) > 250
            else job.description,
        )

        return ApplicationPackage(
            application_id=app.id,
            user_id=app.user_id,
            workflow_thread_id=app.workflow_thread_id,
            job=job_details,
            original_application_url=job.canonical_url,
            resume=resume_summary,
            cover_letter=cover_summary,
            form_answers=answers,
            provider_capability=provider_cap,
            submission_method=submission_method,
            package_hash=current_hash,
            approval_status=app.approval_status,
            approval_notes=app.approval_notes,
            approved_at=app.approved_at,
            approved_package_hash=app.approved_package_hash,
            is_content_altered_since_approval=is_altered,
            last_error=app.last_error,
        )

    async def update_form_answers(
        self,
        session: AsyncSession,
        user_id: int,
        application_id: int,
        answers: ProposedFormAnswers,
    ) -> ApplicationPackage:
        """Update candidate proposed form answers, invalidating any previous approval."""
        stmt = select(JobApplication).where(
            JobApplication.id == application_id,
            JobApplication.user_id == user_id,
        )
        app = (await session.execute(stmt)).scalar_one_or_none()
        if not app:
            raise ValueError(f"Application {application_id} not found or access denied")

        app.form_answers = answers.model_dump()

        # If previously approved, content change MUST invalidate approval
        if app.approval_status == "approved":
            app.approval_status = "invalidated"
            app.status = "awaiting_approval"
            app.approval_notes = (
                "Approval invalidated: form answers were modified after review."
            )

            # Record audit log
            session.add(
                WorkflowExecutionLog(
                    application_id=app.id,
                    thread_id=app.workflow_thread_id,
                    node_name="approval_invalidation",
                    status="completed",
                    details={"reason": "Form answers modified after human review"},
                    error_message="Form answers modified after approval; re-review required",
                    created_at=datetime.now(UTC),
                )
            )

        await session.commit()
        return await self.prepare_package(session, user_id, application_id)

    async def update_document_selection(
        self,
        session: AsyncSession,
        user_id: int,
        application_id: int,
        resume_version_id: int | None = None,
        cover_letter_version_id: int | None = None,
    ) -> ApplicationPackage:
        """Select different resume or cover letter version, invalidating any previous approval."""
        stmt = select(JobApplication).where(
            JobApplication.id == application_id,
            JobApplication.user_id == user_id,
        )
        app = (await session.execute(stmt)).scalar_one_or_none()
        if not app:
            raise ValueError(f"Application {application_id} not found or access denied")

        changed = False
        if resume_version_id and resume_version_id != app.resume_version_id:
            app.resume_version_id = resume_version_id
            changed = True
        if (
            cover_letter_version_id
            and cover_letter_version_id != app.cover_letter_version_id
        ):
            app.cover_letter_version_id = cover_letter_version_id
            changed = True

        if changed and app.approval_status == "approved":
            app.approval_status = "invalidated"
            app.status = "awaiting_approval"
            app.approval_notes = "Approval invalidated: document version selection modified after review."
            session.add(
                WorkflowExecutionLog(
                    application_id=app.id,
                    thread_id=app.workflow_thread_id,
                    node_name="approval_invalidation",
                    status="completed",
                    details={"reason": "Document version modified after human review"},
                    error_message="Document version changed after approval; re-review required",
                    created_at=datetime.now(UTC),
                )
            )

        await session.commit()
        return await self.prepare_package(session, user_id, application_id)

    async def record_human_approval(
        self,
        session: AsyncSession,
        user_id: int,
        application_id: int,
        approval_req: ApplicationApprovalReviewRequest,
    ) -> ApplicationPackage:
        """Record explicit approval bound to the exact package contents, document versions, and job."""
        stmt = select(JobApplication).where(
            JobApplication.id == application_id,
            JobApplication.user_id == user_id,
        )
        app = (await session.execute(stmt)).scalar_one_or_none()
        if not app:
            raise ValueError(f"Application {application_id} not found or access denied")

        # Security check: approval for Job A cannot authorize Job B
        if approval_req.job_id and approval_req.job_id != app.job_id:
            raise ValueError(
                f"Job mismatch: cannot approve application for job {approval_req.job_id}; target is {app.job_id}"
            )

        package = await self.prepare_package(session, user_id, application_id)

        # Content tampering check: if expected hash provided, verify
        if (
            approval_req.expected_package_hash
            and approval_req.expected_package_hash != package.package_hash
        ):
            raise ValueError(
                "Package content was altered since review was opened. Re-review required."
            )

        now = datetime.now(UTC)
        if approval_req.approved:
            app.approval_status = "approved"
            app.status = "approved"
            app.approved_at = now
            app.approved_package_hash = package.package_hash
            app.approval_notes = approval_req.notes
            app.approval_snapshot = {
                "job_id": app.job_id,
                "resume_version_id": app.resume_version_id,
                "cover_letter_version_id": app.cover_letter_version_id,
                "form_answers": app.form_answers,
                "submission_method": package.submission_method,
                "package_hash": package.package_hash,
                "approved_by": user_id,
                "approved_at": now.isoformat(),
            }

            session.add(
                WorkflowExecutionLog(
                    application_id=app.id,
                    thread_id=app.workflow_thread_id,
                    node_name="human_review_approval",
                    status="completed",
                    details={
                        "action": "approved",
                        "actor_id": f"user_{user_id}",
                        "package_hash": package.package_hash,
                        "job_id": app.job_id,
                        "resume_version_id": app.resume_version_id,
                        "cover_letter_version_id": app.cover_letter_version_id,
                        "notes": approval_req.notes,
                    },
                    created_at=now,
                )
            )
        else:
            app.approval_status = "rejected"
            app.status = "rejected"
            app.approval_notes = (
                approval_req.notes
                or "Candidate rejected application packet during review"
            )

            session.add(
                WorkflowExecutionLog(
                    application_id=app.id,
                    thread_id=app.workflow_thread_id,
                    node_name="human_review_approval",
                    status="completed",
                    details={
                        "action": "rejected",
                        "actor_id": f"user_{user_id}",
                        "notes": approval_req.notes,
                    },
                    created_at=now,
                )
            )

        await session.commit()
        return await self.prepare_package(session, user_id, application_id)

    async def submit_application(
        self,
        session: AsyncSession,
        user_id: int,
        application_id: int,
        submit_req: ApplicationSubmitRequest,
        context: dict[str, Any] | None = None,
    ) -> SubmissionResult:
        """Execute authorized submission or generate manual handoff with duplicate prevention."""
        ctx = dict(context or {})

        stmt = select(JobApplication).where(
            JobApplication.id == application_id,
            JobApplication.user_id == user_id,
        )
        app = (await session.execute(stmt)).scalar_one_or_none()
        if not app:
            raise ValueError(f"Application {application_id} not found or access denied")

        # 1. State integrity check: rejected/cancelled applications cannot be submitted
        if app.status in ["rejected", "cancelled"]:
            raise UnauthorizedSubmissionError(
                f"Cannot submit an application with status '{app.status}'"
            )

        # 2. Strict approval check: human approval MUST be active
        if app.approval_status != "approved":
            raise UnauthorizedSubmissionError(
                f"Cannot submit application: human approval is not granted (current status is '{app.approval_status}')"
            )

        # 3. Job mismatch security check
        if submit_req.target_job_id and submit_req.target_job_id != app.job_id:
            raise UnauthorizedSubmissionError(
                f"Job authorization mismatch: approved for job {app.job_id}, cannot submit for job {submit_req.target_job_id}"
            )

        # 4. Check package content integrity
        package = await self.prepare_package(session, user_id, application_id)
        if package.package_hash != app.approved_package_hash:
            app.approval_status = "invalidated"
            app.status = "awaiting_approval"
            await session.commit()
            raise UnauthorizedSubmissionError(
                "Application approval is invalidated because content changed since review. Re-approval required."
            )

        # 5. Prevent blind resubmission if confirmation is currently pending
        if app.status == "confirmation_pending":
            raise BlindResubmissionError(
                "A previous submission attempt is currently pending confirmation from the provider. Blind resubmissions are blocked to prevent duplicate applications."
            )

        # 6. Database duplicate attempt constraint check using unique submission_key
        sub_key = submit_req.submission_key.strip()
        if not sub_key:
            raise ValueError("A unique submission_key must be provided")

        attempt = ApplicationSubmissionAttempt(
            application_id=app.id,
            user_id=user_id,
            submission_key=sub_key,
            actor_id=f"user_{user_id}",
            provider_id=package.job.source,
            submission_method=package.submission_method,
            status="started",
            package_hash=package.package_hash,
            resume_version_id=app.resume_version_id,
            cover_letter_version_id=app.cover_letter_version_id,
            form_answers_snapshot=redact_sensitive_value(app.form_answers),
            started_at=datetime.now(UTC),
        )
        session.add(attempt)

        try:
            # Flushes attempt into DB to enforce UniqueConstraint("submission_key")
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise DuplicateSubmissionError(
                f"Duplicate submission attempt detected for key '{sub_key}'. Attempt already exists."
            )

        # 7. Execute submission via provider adapter
        adapter = submission_registry.get_adapter(package.job.source)
        res = await adapter.submit(package, sub_key, ctx)

        now = datetime.now(UTC)
        attempt.status = res.status
        attempt.completed_at = now
        attempt.receipt_reference = res.receipt_reference
        attempt.error_message = res.error_message
        attempt.blind_resubmission_prevented = res.blind_resubmission_prevented
        attempt.response_payload = redact_sensitive_value(res.response_payload)

        if res.status == "submitted":
            app.status = "submitted"
            app.tracking_metadata = {
                "confirmation_reference": res.receipt_reference,
                "submitted_at": now.isoformat(),
                "provider": package.job.source,
                "submission_method": "automated_api",
            }
        elif res.status == "manual_handoff":
            app.status = "manual_handoff"
            app.tracking_metadata = res.response_payload
        elif res.status == "confirmation_pending":
            app.status = "confirmation_pending"
            app.last_error = res.error_message
            app.tracking_metadata = {
                "confirmation_pending": True,
                "submission_key": sub_key,
                "attempted_at": now.isoformat(),
            }
        elif res.status == "failed":
            app.status = "failed"
            app.last_error = res.error_message

        # Record audit log
        session.add(
            WorkflowExecutionLog(
                application_id=app.id,
                thread_id=app.workflow_thread_id,
                node_name="application_submission",
                status=res.status,
                details={
                    "actor_id": f"user_{user_id}",
                    "submission_key": sub_key,
                    "provider": package.job.source,
                    "submission_method": package.submission_method,
                    "receipt_reference": res.receipt_reference,
                    "resume_version_id": app.resume_version_id,
                    "cover_letter_version_id": app.cover_letter_version_id,
                    "package_hash": package.package_hash,
                },
                error_message=res.error_message,
                created_at=now,
            )
        )

        await session.commit()
        await session.refresh(app)
        return res

    async def get_submission_attempts(
        self,
        session: AsyncSession,
        user_id: int,
        application_id: int,
    ) -> list[SubmissionAttemptResponse]:
        """Fetch all submission attempts for an application with ownership verification."""
        stmt = select(JobApplication).where(
            JobApplication.id == application_id,
            JobApplication.user_id == user_id,
        )
        app = (await session.execute(stmt)).scalar_one_or_none()
        if not app:
            raise ValueError(f"Application {application_id} not found or access denied")

        att_stmt = (
            select(ApplicationSubmissionAttempt)
            .where(ApplicationSubmissionAttempt.application_id == application_id)
            .order_by(ApplicationSubmissionAttempt.started_at.desc())
        )
        attempts = (await session.execute(att_stmt)).scalars().all()
        return [SubmissionAttemptResponse.model_validate(a) for a in attempts]


submission_service = SubmissionService()

