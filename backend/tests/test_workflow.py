"""Comprehensive tests for Phase 6 LangGraph workflow, durable checkpointing, and human approval."""

import uuid
from datetime import datetime, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import MemorySaver

from app.core.database import async_session_factory
from app.main import app
from app.models.entities import (
    JobApplication,
    JobPosting,
    Profile,
    Skill,
    User,
    WorkflowExecutionLog,
)
from app.services.documents.document_service import DocumentService
from app.services.documents.schemas import DocumentUpdateRequest
from app.services.workflow.checkpointer import reset_checkpointer_for_testing
from app.services.workflow.redactor import RedactingLangSmithTracer, redact_sensitive_value
from app.services.workflow.schemas import ApplicationApprovalRequest, ApplicationStartRequest
from app.services.workflow.service import WorkflowService


@pytest.fixture(autouse=True)
def setup_test_checkpointer():
    """Ensure an isolated in-memory checkpointer is used for deterministic test execution."""
    saver = MemorySaver()
    reset_checkpointer_for_testing(saver)
    yield saver
    reset_checkpointer_for_testing(None)


async def _create_test_candidate_user(email_prefix: str = "wf_user") -> User:
    """Helper creating a test candidate with verified profile facts."""
    uid = uuid.uuid4().hex[:8]
    email = f"{email_prefix}_{uid}@example.com"
    async with async_session_factory() as session:
        user = User(
            email=email,
            hashed_password="hashed_test_password_123",
            full_name=f"Workflow Tester {uid}",
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        profile = Profile(
            user_id=user.id,
            headline="Senior Backend & Distributed Systems Engineer",
            target_job_titles=["Senior Software Engineer", "Backend Engineer"],
            location="Remote",
            remote_preference="remote",
            work_authorization_status="citizen",
            profile_version=1,
        )
        session.add(profile)

        skill1 = Skill(user_id=user.id, name="Python", proficiency_level="expert", years_experience=6.0)
        skill2 = Skill(user_id=user.id, name="PostgreSQL", proficiency_level="advanced", years_experience=5.0)
        session.add_all([skill1, skill2])
        await session.commit()
        await session.refresh(user)
        return user


async def _create_test_job(source_id: str = "wf-job-01") -> JobPosting:
    """Helper creating a test job posting."""
    uid = uuid.uuid4().hex[:8]
    async with async_session_factory() as session:
        job = JobPosting(
            source="manual_import",
            source_id=f"{source_id}-{uid}",
            canonical_url=f"https://jobs.example.com/roles/{uid}",
            title="Senior Distributed Systems Engineer",
            company="CloudScale Corp",
            description="We are seeking a Senior Backend Engineer proficient in Python and PostgreSQL to build distributed architectures.",
            location="Remote",
            work_mode="remote",
            employment_type="full_time",
            retrieved_at=datetime.now(timezone.utc),
            is_active=True,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


@pytest.mark.asyncio
async def test_workflow_progresses_and_pauses_before_submission():
    """Verify workflow executes from discovery through document validation and pauses for approval."""
    user = await _create_test_candidate_user("wf_progress")
    job = await _create_test_job("job_progress")
    service = WorkflowService()

    idempotency_key = f"key_{uuid.uuid4().hex}"
    req = ApplicationStartRequest(
        job_id=job.id,
        template_id="modern",
        submission_mode="manual_handoff",
        idempotency_key=idempotency_key,
    )

    async with async_session_factory() as session:
        app_record = await service.start_workflow(session, user.id, req)

    # 1. Verify workflow paused at human approval gate
    assert app_record.status == "awaiting_approval"
    assert app_record.approval_status == "pending"
    assert app_record.resume_document_id is not None
    assert app_record.cover_letter_document_id is not None
    assert app_record.application_payload is not None
    assert app_record.application_payload.get("target_company") == "CloudScale Corp"

    # 2. Verify execution logs recorded each completed node
    async with async_session_factory() as session:
        logs = await service.get_workflow_history(session, user.id, app_record.id)
    node_names = [log.node_name for log in logs]
    assert "discover_job" in node_names
    assert "normalize_job" in node_names
    assert "deduplicate_job" in node_names
    assert "match_candidate" in node_names
    assert "generate_documents" in node_names
    assert "validate_quality" in node_names
    assert "prepare_application" in node_names
    assert "human_approval" in node_names


@pytest.mark.asyncio
async def test_approval_resumes_workflow_after_process_restart():
    """Verify approval resumes an interrupted workflow and completes tracking after a simulated restart."""
    user = await _create_test_candidate_user("wf_resume")
    job = await _create_test_job("job_resume")

    # Start with checkpointer A
    saver = MemorySaver()
    service_a = WorkflowService(checkpointer=saver)

    idempotency_key = f"restart_{uuid.uuid4().hex}"
    req = ApplicationStartRequest(
        job_id=job.id,
        idempotency_key=idempotency_key,
        submission_mode="manual_handoff",
    )

    async with async_session_factory() as session:
        app_record = await service_a.start_workflow(session, user.id, req)
    assert app_record.status == "awaiting_approval"

    # Simulate process restart: instantiate a new service instance reusing the durable checkpointer state
    service_b = WorkflowService(checkpointer=saver)
    approval_req = ApplicationApprovalRequest(
        approved=True,
        notes="All tailored bullet points verified and approved for submission.",
    )

    async with async_session_factory() as session:
        resumed_app = await service_b.resume_workflow_approval(session, user.id, app_record.id, approval_req)

    # Workflow must have progressed through submission and tracking
    assert resumed_app.approval_status == "approved"
    assert resumed_app.status in ["manual_handoff", "submitted"]
    assert resumed_app.tracking_metadata is not None
    assert resumed_app.tracking_metadata.get("workflow_completed") is True
    assert "confirmation_reference" in resumed_app.tracking_metadata


@pytest.mark.asyncio
async def test_rejection_and_cancellation_prevent_submission():
    """Verify that human rejection and cancellation terminate workflow without submitting."""
    user = await _create_test_candidate_user("wf_reject")
    job = await _create_test_job("job_reject")
    service = WorkflowService()

    # 1. Test human rejection
    req = ApplicationStartRequest(job_id=job.id)
    async with async_session_factory() as session:
        app1 = await service.start_workflow(session, user.id, req)

    rejection = ApplicationApprovalRequest(approved=False, notes="Skills emphasis does not match my preference")
    async with async_session_factory() as session:
        rejected_app = await service.resume_workflow_approval(session, user.id, app1.id, rejection)

    assert rejected_app.approval_status == "rejected"
    assert rejected_app.status == "rejected"
    assert rejected_app.tracking_metadata.get("workflow_completed") is not True

    # 2. Test explicit cancellation
    req2 = ApplicationStartRequest(job_id=job.id)
    async with async_session_factory() as session:
        app2 = await service.start_workflow(session, user.id, req2)
        cancelled_app = await service.cancel_workflow(session, user.id, app2.id, "Candidate withdrew application")

    assert cancelled_app.status == "cancelled"
    assert cancelled_app.approval_status == "rejected"


@pytest.mark.asyncio
async def test_document_edit_invalidates_prior_human_approval():
    """Verify that editing an approved document automatically invalidates approval."""
    user = await _create_test_candidate_user("wf_invalidate")
    job = await _create_test_job("job_invalidate")
    service = WorkflowService()

    req = ApplicationStartRequest(job_id=job.id)
    async with async_session_factory() as session:
        app_record = await service.start_workflow(session, user.id, req)

    # Human approves initial version
    approval = ApplicationApprovalRequest(approved=True, notes="Approved v1")
    async with async_session_factory() as session:
        approved_app = await service.resume_workflow_approval(session, user.id, app_record.id, approval)
    assert approved_app.approval_status == "approved"

    # User now edits the resume attached to this application
    doc_service = DocumentService()
    async with async_session_factory() as session:
        new_version = await doc_service.edit_document_content(
            session=session,
            user_id=user.id,
            document_id=approved_app.resume_document_id,  # type: ignore
            update_data=DocumentUpdateRequest(
                structured_data={
                    "full_name": user.full_name,
                    "email": user.email,
                    "target_title": job.title,
                    "target_company": job.company,
                    "professional_summary": "Revised summary with additional verified metrics.",
                    "highlighted_skills": ["Python", "PostgreSQL"],
                    "experience": [],
                    "projects": [],
                    "education": [],
                    "certifications": [],
                },
                change_summary="User manual bullet point edit",
            ),
        )
        # Trigger invalidation hook
        invalidated_ids = await service.invalidate_approval_on_document_edit(
            session, user.id, approved_app.resume_document_id, new_version.id  # type: ignore
        )

    assert approved_app.id in invalidated_ids
    # Verify approval status is now invalidated and requires re-approval
    async with async_session_factory() as session:
        rechecked_app = await service.get_application(session, user.id, approved_app.id)
    assert rechecked_app is not None
    assert rechecked_app.approval_status == "invalidated"
    assert rechecked_app.status == "awaiting_approval"


@pytest.mark.asyncio
async def test_idempotent_replaying_prevents_duplicate_applications():
    """Verify replaying workflow with same idempotency key returns existing application."""
    user = await _create_test_candidate_user("wf_idempotent")
    job = await _create_test_job("job_idempotent")
    service = WorkflowService()

    fixed_key = f"idemp_{uuid.uuid4().hex}"
    req = ApplicationStartRequest(
        job_id=job.id,
        idempotency_key=fixed_key,
    )

    async with async_session_factory() as session:
        app1 = await service.start_workflow(session, user.id, req)
        app2 = await service.start_workflow(session, user.id, req)

    # Must be exact same database record
    assert app1.id == app2.id
    assert app1.workflow_thread_id == app2.workflow_thread_id


@pytest.mark.asyncio
async def test_bounded_retries_and_outage_handling():
    """Verify bounded retry limits prevent infinite loops during provider or data outages."""
    user = await _create_test_candidate_user("wf_outage")
    service = WorkflowService()

    # Request invalid non-existent URL causing simulated provider outage
    req = ApplicationStartRequest(
        job_url="https://invalid-non-existent-board.fake/jobs/9999",
    )

    async with async_session_factory() as session:
        failed_app = await service.start_workflow(session, user.id, req)

    assert failed_app.status == "failed"
    assert failed_app.retry_count <= failed_app.max_retries
    assert failed_app.last_error is not None


@pytest.mark.asyncio
async def test_sensitive_data_redaction_and_langsmith_isolation():
    """Verify sensitive tokens and secrets are redacted and tracer errors do not break execution."""
    raw_payload = {
        "user_email": "candidate@example.com",
        "api_key": "sk-1234567890abcdef1234567890abcdef",
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.do_not_leak",
        "password": "secret_cleartext_password",
        "raw_cv_text": "Curriculum Vitae of Candidate: Confidential experience details...",
        "clean_field": "Senior Software Engineer",
    }

    sanitized = redact_sensitive_value(raw_payload)
    assert sanitized["api_key"] == "[REDACTED_CONFIDENTIAL]"
    assert sanitized["access_token"] == "[REDACTED_CONFIDENTIAL]"
    assert sanitized["password"] == "[REDACTED_CONFIDENTIAL]"
    assert sanitized["raw_cv_text"] == "[REDACTED_CONFIDENTIAL]"
    assert sanitized["clean_field"] == "Senior Software Engineer"

    # Test tracer error isolation
    tracer = RedactingLangSmithTracer()
    # Passing an un-serializable object or triggering an internal fault must not crash
    tracer._persist_run(None)  # type: ignore


@pytest.mark.asyncio
async def test_api_endpoints_cross_user_isolation():
    """Verify users cannot view, approve, or cancel another user's applications."""
    user_a = await _create_test_candidate_user("user_a")
    user_b = await _create_test_candidate_user("user_b")
    job = await _create_test_job("job_iso")
    service = WorkflowService()

    async with async_session_factory() as session:
        app_a = await service.start_workflow(session, user_a.id, ApplicationStartRequest(job_id=job.id))

    # User B attempts to access User A's application
    async with async_session_factory() as session:
        # Check get_application
        retrieved = await service.get_application(session, user_b.id, app_a.id)
        assert retrieved is None

        # Check approval rejection for unauthorized user
        with pytest.raises(ValueError):
            await service.resume_workflow_approval(
                session, user_b.id, app_a.id, ApplicationApprovalRequest(approved=True)
            )

        # Check cancellation rejection for unauthorized user
        with pytest.raises(ValueError):
            await service.cancel_workflow(session, user_b.id, app_a.id)
