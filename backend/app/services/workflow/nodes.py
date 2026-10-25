"""Individual execution nodes for the Phase 6 LangGraph workflow."""

import logging
from datetime import UTC, datetime
from typing import Any

from langgraph.types import interrupt
from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.entities import (
    DocumentVersion,
    JobApplication,
    JobPosting,
    WorkflowExecutionLog,
)
from app.services.documents.document_service import DocumentService
from app.services.documents.factual_checker import FactualConsistencyChecker
from app.services.job_service import JobService
from app.services.matching.engine import DeterministicMatchingEngine
from app.services.workflow.redactor import redact_sensitive_value
from app.services.workflow.schemas import WorkflowState

logger = logging.getLogger(__name__)


class UnauthorizedSubmissionError(Exception):
    """Raised when submission is attempted without verified human approval."""


async def _log_node_execution(
    application_id: int | None,
    thread_id: str,
    node_name: str,
    status: str,
    details: dict[str, Any],
    error_message: str | None = None,
    attempt: int = 1,
) -> None:
    """Record an immutable execution log entry with sensitive data redacted."""
    if not application_id:
        return
    try:
        async with async_session_factory() as session:
            sanitized_details = redact_sensitive_value(details)
            log = WorkflowExecutionLog(
                application_id=application_id,
                thread_id=thread_id,
                node_name=node_name,
                status=status,
                details=sanitized_details
                if isinstance(sanitized_details, dict)
                else {"summary": str(sanitized_details)},
                error_message=error_message,
                attempt_number=attempt,
                created_at=datetime.now(UTC),
            )
            session.add(log)
            await session.commit()
    except Exception as exc:
        logger.warning(
            "Could not persist execution log for node %s: %s", node_name, exc
        )


async def discover_job_node(state: WorkflowState) -> dict[str, Any]:
    """Node 1: Discover or retrieve job details from URL or provider."""
    thread_id = state.get("thread_id", "")
    app_id = state.get("application_id")
    attempt = state.get("retry_count", 0) + 1

    await _log_node_execution(
        app_id,
        thread_id,
        "discover_job",
        "started",
        {"input_url": state.get("raw_job_url")},
        attempt=attempt,
    )

    job_data: dict[str, Any] | None = state.get("job_data")
    job_id = state.get("job_id")
    raw_url = state.get("raw_job_url")

    try:
        if job_id and not job_data:
            async with async_session_factory() as session:
                stmt = select(JobPosting).where(JobPosting.id == job_id)
                res = await session.execute(stmt)
                db_job = res.scalar_one_or_none()
                if db_job:
                    job_data = {
                        "id": db_job.id,
                        "title": db_job.title,
                        "company": db_job.company,
                        "description": db_job.description,
                        "location": db_job.location,
                        "work_mode": db_job.work_mode,
                        "employment_type": db_job.employment_type,
                        "canonical_url": db_job.canonical_url,
                        "source": db_job.source,
                        "source_id": db_job.source_id,
                    }

        if not job_data and raw_url:
            async with async_session_factory() as session:
                imported_job = await JobService.import_url(session, raw_url)
                job_id = imported_job.id
                job_data = {
                    "id": imported_job.id,
                    "title": imported_job.title,
                    "company": imported_job.company,
                    "description": imported_job.description,
                    "location": imported_job.location,
                    "work_mode": imported_job.work_mode,
                    "employment_type": imported_job.employment_type,
                    "canonical_url": imported_job.canonical_url,
                    "source": imported_job.source,
                    "source_id": imported_job.source_id,
                }

        if not job_data:
            raise ValueError(
                "No valid job input provided (missing job_id, URL, or provider details)"
            )

        await _log_node_execution(
            app_id,
            thread_id,
            "discover_job",
            "completed",
            {"title": job_data.get("title")},
            attempt=attempt,
        )
        return {
            "job_data": job_data,
            "job_id": job_id,
            "status": "discovered",
            "last_error": None,
        }
    except Exception as exc:
        err = f"Discovery failed: {str(exc)}"
        logger.error(err)
        await _log_node_execution(
            app_id,
            thread_id,
            "discover_job",
            "failed",
            {},
            error_message=err,
            attempt=attempt,
        )
        return {"last_error": err, "status": "failed", "retry_count": attempt}


async def normalize_job_node(state: WorkflowState) -> dict[str, Any]:
    """Node 2: Normalize job details into standard format."""
    thread_id = state.get("thread_id", "")
    app_id = state.get("application_id")
    attempt = state.get("retry_count", 0) + 1

    await _log_node_execution(
        app_id, thread_id, "normalize_job", "started", {}, attempt=attempt
    )
    job_data = dict(state.get("job_data") or {})

    # Ensure required normalized attributes
    job_data["title"] = str(job_data.get("title", "")).strip() or "Untitled Position"
    job_data["company"] = (
        str(job_data.get("company", "")).strip() or "Unknown Organization"
    )
    job_data["work_mode"] = (
        str(job_data.get("work_mode", "unspecified")).lower().strip()
    )
    job_data["employment_type"] = (
        str(job_data.get("employment_type", "full_time")).lower().strip()
    )
    job_data["description"] = str(job_data.get("description", "")).strip()

    await _log_node_execution(
        app_id,
        thread_id,
        "normalize_job",
        "completed",
        {"normalized_title": job_data["title"]},
        attempt=attempt,
    )
    return {
        "job_data": job_data,
        "status": "normalized",
    }


async def deduplicate_job_node(state: WorkflowState) -> dict[str, Any]:
    """Node 3: Check database for existing job posting and attach or persist idempotently."""
    thread_id = state.get("thread_id", "")
    app_id = state.get("application_id")
    attempt = state.get("retry_count", 0) + 1

    await _log_node_execution(
        app_id, thread_id, "deduplicate_job", "started", {}, attempt=attempt
    )
    job_data = state.get("job_data") or {}
    job_id = state.get("job_id")
    is_duplicate = False

    try:
        async with async_session_factory() as session:
            # If job_id was already determined, verify it exists
            if job_id:
                stmt = select(JobPosting).where(JobPosting.id == job_id)
                res = await session.execute(stmt)
                db_job = res.scalar_one_or_none()
                if db_job:
                    is_duplicate = True
            else:
                # Deduplicate by canonical URL or (source, source_id)
                canonical_url = job_data.get("canonical_url")
                source = job_data.get("source", "manual_import")
                source_id = job_data.get("source_id", canonical_url)

                stmt = select(JobPosting).where(
                    (JobPosting.canonical_url == canonical_url)
                    | (
                        (JobPosting.source == source)
                        & (JobPosting.source_id == source_id)
                    )
                )
                res = await session.execute(stmt)
                db_job = res.scalar_one_or_none()

                if db_job:
                    job_id = db_job.id
                    is_duplicate = True
                else:
                    new_job = JobPosting(
                        source=source,
                        source_id=source_id
                        or f"imp-{datetime.now(UTC).timestamp()}",
                        canonical_url=canonical_url
                        or f"https://example.com/jobs/{source_id}",
                        title=job_data.get("title", "Position"),
                        company=job_data.get("company", "Company"),
                        description=job_data.get("description", ""),
                        location=job_data.get("location"),
                        work_mode=job_data.get("work_mode", "unspecified"),
                        employment_type=job_data.get("employment_type", "full_time"),
                        retrieved_at=datetime.now(UTC),
                        is_active=True,
                    )
                    session.add(new_job)
                    await session.commit()
                    await session.refresh(new_job)
                    job_id = new_job.id

            # Update application job_id
            if app_id:
                app_stmt = select(JobApplication).where(JobApplication.id == app_id)
                app_res = await session.execute(app_stmt)
                app = app_res.scalar_one_or_none()
                if app:
                    app.job_id = job_id
                    await session.commit()

        await _log_node_execution(
            app_id,
            thread_id,
            "deduplicate_job",
            "completed",
            {"job_id": job_id, "is_duplicate": is_duplicate},
            attempt=attempt,
        )
        return {
            "job_id": job_id,
            "is_duplicate": is_duplicate,
            "status": "deduplicated",
        }
    except Exception as exc:
        err = f"Deduplication failed: {str(exc)}"
        logger.error(err)
        await _log_node_execution(
            app_id,
            thread_id,
            "deduplicate_job",
            "failed",
            {},
            error_message=err,
            attempt=attempt,
        )
        return {"last_error": err, "status": "failed", "retry_count": attempt}


async def match_candidate_node(state: WorkflowState) -> dict[str, Any]:
    """Node 4: Deterministic candidate matching against job posting."""
    thread_id = state.get("thread_id", "")
    app_id = state.get("application_id")
    user_id = state.get("user_id")
    job_id = state.get("job_id")
    attempt = state.get("retry_count", 0) + 1

    await _log_node_execution(
        app_id,
        thread_id,
        "match_candidate",
        "started",
        {"user_id": user_id, "job_id": job_id},
        attempt=attempt,
    )

    try:
        async with async_session_factory() as session:
            # Load candidate facts using DocumentService utility
            candidate_user = await DocumentService.load_candidate_facts(
                session, user_id or 0
            )

            # Load job posting
            job_stmt = select(JobPosting).where(JobPosting.id == job_id)
            job_res = await session.execute(job_stmt)
            job = job_res.scalar_one_or_none()

            if not candidate_user or not job:
                raise ValueError("Candidate user or job posting not found for matching")

            engine = DeterministicMatchingEngine()
            evaluation = engine.evaluate_match(candidate_user, job)
            score = evaluation.total_score
            meets_threshold = score >= 20.0  # Initial matching threshold

            match_details = {
                "score": score,
                "explanation": evaluation.explanation,
                "matched_skills": [
                    m["skill"] for m in evaluation.matched_skills if "skill" in m
                ],
                "missing_skills": evaluation.missing_skills,
            }

            if app_id:
                app_stmt = select(JobApplication).where(JobApplication.id == app_id)
                app_res = await session.execute(app_stmt)
                app = app_res.scalar_one_or_none()
                if app:
                    app.status = "matched"
                    await session.commit()

        await _log_node_execution(
            app_id,
            thread_id,
            "match_candidate",
            "completed",
            match_details,
            attempt=attempt,
        )
        return {
            "match_score": score,
            "match_details": match_details,
            "meets_threshold": meets_threshold,
            "status": "matched" if meets_threshold else "below_threshold",
        }
    except Exception as exc:
        err = f"Matching failed: {str(exc)}"
        logger.error(err)
        await _log_node_execution(
            app_id,
            thread_id,
            "match_candidate",
            "failed",
            {},
            error_message=err,
            attempt=attempt,
        )
        return {"last_error": err, "status": "failed", "retry_count": attempt}


async def generate_documents_node(state: WorkflowState) -> dict[str, Any]:
    """Node 5: Generate tailored resume and cover letter strictly grounded in verified facts."""
    thread_id = state.get("thread_id", "")
    app_id = state.get("application_id")
    user_id = state.get("user_id") or 0
    job_id = state.get("job_id") or 0
    template_id = state.get("template_id", "modern")
    attempt = state.get("retry_count", 0) + 1

    await _log_node_execution(
        app_id,
        thread_id,
        "generate_documents",
        "started",
        {"template": template_id},
        attempt=attempt,
    )

    try:
        async with async_session_factory() as session:
            # 1. Generate tailored resume (returns tuple of (GeneratedDocument, DocumentVersion))
            resume_doc, resume_ver = await DocumentService.generate_document(
                session=session,
                user_id=user_id,
                job_id=job_id,
                doc_type="resume",
                template_id=template_id,
                custom_instructions=state.get("custom_instructions"),
            )
            resume_doc_id = resume_doc.id
            resume_v_id = resume_ver.id

            # 2. Generate tailored cover letter
            cover_doc, cover_ver = await DocumentService.generate_document(
                session=session,
                user_id=user_id,
                job_id=job_id,
                doc_type="cover_letter",
                template_id=template_id,
                custom_instructions=state.get("custom_instructions"),
            )
            cover_doc_id = cover_doc.id
            cover_v_id = cover_ver.id

            # Update application record
            if app_id:
                app_stmt = select(JobApplication).where(JobApplication.id == app_id)
                app_res = await session.execute(app_stmt)
                app = app_res.scalar_one_or_none()
                if app:
                    app.resume_document_id = resume_doc_id
                    app.resume_version_id = resume_v_id
                    app.cover_letter_document_id = cover_doc_id
                    app.cover_letter_version_id = cover_v_id
                    app.status = "documents_generated"
                    await session.commit()

        await _log_node_execution(
            app_id,
            thread_id,
            "generate_documents",
            "completed",
            {"resume_id": resume_doc_id, "cover_letter_id": cover_doc_id},
            attempt=attempt,
        )
        return {
            "resume_document_id": resume_doc_id,
            "resume_version_id": resume_v_id,
            "cover_letter_document_id": cover_doc_id,
            "cover_letter_version_id": cover_v_id,
            "status": "documents_generated",
        }
    except Exception as exc:
        err = f"Document generation failed: {str(exc)}"
        logger.error(err)
        await _log_node_execution(
            app_id,
            thread_id,
            "generate_documents",
            "failed",
            {},
            error_message=err,
            attempt=attempt,
        )
        return {"last_error": err, "status": "failed", "retry_count": attempt}


async def validate_quality_node(state: WorkflowState) -> dict[str, Any]:
    """Node 6: Run automated factual consistency check identifying unverified claims."""
    thread_id = state.get("thread_id", "")
    app_id = state.get("application_id")
    attempt = state.get("retry_count", 0) + 1

    await _log_node_execution(
        app_id, thread_id, "validate_quality", "started", {}, attempt=attempt
    )

    try:
        resume_v_id = state.get("resume_version_id")
        user_id = state.get("user_id") or 0

        async with async_session_factory() as session:
            # Load candidate verified facts
            candidate_user = await DocumentService.load_candidate_facts(
                session, user_id
            )

            # Load generated resume version
            ver_stmt = select(DocumentVersion).where(DocumentVersion.id == resume_v_id)
            ver_res = await session.execute(ver_stmt)
            v = ver_res.scalar_one_or_none()

            if not candidate_user or not v:
                raise ValueError(
                    "Candidate user or document version not found for validation"
                )

            from app.services.documents.schemas import StructuredResume

            s_resume = StructuredResume(**v.structured_data)
            report = FactualConsistencyChecker.verify_resume(s_resume, candidate_user)

            validation_passed = (
                report.is_clean and report.factual_confidence_score >= 80.0
            )
            quality_report = report.model_dump()

        await _log_node_execution(
            app_id,
            thread_id,
            "validate_quality",
            "completed",
            {"is_clean": report.is_clean, "score": report.factual_confidence_score},
            attempt=attempt,
        )
        return {
            "quality_report": quality_report,
            "validation_passed": validation_passed,
            "status": "validated" if validation_passed else "validation_failed",
        }
    except Exception as exc:
        err = f"Quality validation failed: {str(exc)}"
        logger.error(err)
        await _log_node_execution(
            app_id,
            thread_id,
            "validate_quality",
            "failed",
            {},
            error_message=err,
            attempt=attempt,
        )
        return {"last_error": err, "status": "failed", "retry_count": attempt}


async def prepare_application_node(state: WorkflowState) -> dict[str, Any]:
    """Node 7: Prepare application packet and transition to awaiting approval."""
    thread_id = state.get("thread_id", "")
    app_id = state.get("application_id")
    attempt = state.get("retry_count", 0) + 1

    await _log_node_execution(
        app_id, thread_id, "prepare_application", "started", {}, attempt=attempt
    )

    try:
        job_data = state.get("job_data") or {}
        payload = {
            "target_company": job_data.get("company"),
            "target_title": job_data.get("title"),
            "job_url": job_data.get("canonical_url"),
            "resume_version_id": state.get("resume_version_id"),
            "cover_letter_version_id": state.get("cover_letter_version_id"),
            "submission_mode": state.get("submission_mode", "manual_handoff"),
            "prepared_at": datetime.now(UTC).isoformat(),
        }

        async with async_session_factory() as session:
            if app_id:
                app_stmt = select(JobApplication).where(JobApplication.id == app_id)
                app_res = await session.execute(app_stmt)
                app = app_res.scalar_one_or_none()
                if app:
                    app.application_payload = payload
                    app.status = "awaiting_approval"
                    app.approval_status = "pending"
                    await session.commit()

        await _log_node_execution(
            app_id,
            thread_id,
            "prepare_application",
            "completed",
            payload,
            attempt=attempt,
        )
        return {
            "application_payload": payload,
            "status": "awaiting_approval",
        }
    except Exception as exc:
        err = f"Application preparation failed: {str(exc)}"
        logger.error(err)
        await _log_node_execution(
            app_id,
            thread_id,
            "prepare_application",
            "failed",
            {},
            error_message=err,
            attempt=attempt,
        )
        return {"last_error": err, "status": "failed", "retry_count": attempt}


async def human_approval_node(state: WorkflowState) -> dict[str, Any]:
    """Node 8: Human approval interrupt gate. Pauses execution until explicit review."""
    thread_id = state.get("thread_id", "")
    app_id = state.get("application_id")
    human_approved = state.get("human_approved")

    # If human approval has not been decided yet, INTERRUPT graph execution
    if human_approved is None:
        await _log_node_execution(
            app_id,
            thread_id,
            "human_approval",
            "interrupted",
            {"prompt": "Human approval required before application submission"},
        )
        # LangGraph interrupt: suspends graph state and awaits resume command
        decision = interrupt(
            {
                "message": "Human approval required before submission",
                "application_id": app_id,
                "thread_id": thread_id,
                "application_payload": state.get("application_payload"),
            }
        )
        if isinstance(decision, dict):
            human_approved = decision.get("approved", False)
            state["approval_notes"] = decision.get("notes")

    # Process decision after resume
    status_str = "approved" if human_approved else "rejected"
    async with async_session_factory() as session:
        if app_id:
            app_stmt = select(JobApplication).where(JobApplication.id == app_id)
            app_res = await session.execute(app_stmt)
            app = app_res.scalar_one_or_none()
            if app:
                app.approval_status = status_str
                app.status = status_str
                app.approval_notes = state.get("approval_notes")
                if human_approved:
                    app.approved_at = datetime.now(UTC)
                await session.commit()

    await _log_node_execution(
        app_id,
        thread_id,
        "human_approval",
        "completed",
        {"human_approved": human_approved, "status": status_str},
    )
    return {
        "human_approved": human_approved,
        "status": status_str,
    }


async def submit_or_handoff_node(state: WorkflowState) -> dict[str, Any]:
    """Node 9: Strictly authorized submission or manual handoff packet generation."""
    thread_id = state.get("thread_id", "")
    app_id = state.get("application_id")
    attempt = state.get("retry_count", 0) + 1

    # CRITICAL SECURITY GUARD: Verify human approval in both state and persistent database
    if not state.get("human_approved"):
        raise UnauthorizedSubmissionError(
            "Cannot submit application: human approval is not granted."
        )

    async with async_session_factory() as session:
        if app_id:
            app_stmt = select(JobApplication).where(JobApplication.id == app_id)
            app_res = await session.execute(app_stmt)
            app = app_res.scalar_one_or_none()
            if not app or app.approval_status != "approved":
                raise UnauthorizedSubmissionError(
                    f"Database approval check failed: status is '{app.approval_status if app else 'none'}'"
                )

    await _log_node_execution(
        app_id, thread_id, "submit_or_handoff", "started", {}, attempt=attempt
    )

    submission_mode = state.get("submission_mode", "manual_handoff")
    handoff_packet = {
        "submission_mode": submission_mode,
        "submitted_at": datetime.now(UTC).isoformat(),
        "handoff_instructions": "Review generated documents, verify company portal link, and submit.",
        "verified_approval": True,
    }

    async with async_session_factory() as session:
        if app_id:
            app_stmt = select(JobApplication).where(JobApplication.id == app_id)
            app_res = await session.execute(app_stmt)
            app = app_res.scalar_one_or_none()
            if app:
                app.status = (
                    "submitted"
                    if submission_mode == "automated_api"
                    else "manual_handoff"
                )
                await session.commit()

    await _log_node_execution(
        app_id,
        thread_id,
        "submit_or_handoff",
        "completed",
        handoff_packet,
        attempt=attempt,
    )
    return {
        "status": "submitted"
        if submission_mode == "automated_api"
        else "manual_handoff",
        "tracking_metadata": handoff_packet,
    }


async def tracking_node(state: WorkflowState) -> dict[str, Any]:
    """Node 10: Final tracking, confirmation reference generation, and persistent status."""
    thread_id = state.get("thread_id", "")
    app_id = state.get("application_id")

    tracking_ref = (
        f"CP-APP-{app_id or '0'}-{int(datetime.now(UTC).timestamp())}"
    )
    final_tracking = dict(state.get("tracking_metadata") or {})
    final_tracking["confirmation_reference"] = tracking_ref
    final_tracking["completed_at"] = datetime.now(UTC).isoformat()
    final_tracking["workflow_completed"] = True

    async with async_session_factory() as session:
        if app_id:
            app_stmt = select(JobApplication).where(JobApplication.id == app_id)
            app_res = await session.execute(app_stmt)
            app = app_res.scalar_one_or_none()
            if app:
                app.tracking_metadata = final_tracking
                await session.commit()

    await _log_node_execution(
        app_id, thread_id, "tracking", "completed", {"ref": tracking_ref}
    )
    return {
        "status": "completed",
        "tracking_metadata": final_tracking,
    }
