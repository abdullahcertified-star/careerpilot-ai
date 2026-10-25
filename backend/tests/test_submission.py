"""Comprehensive tests for Phase 7: Secure application preparation, human review, and permitted submission.

Preconditions & Requirements:
1. Submission without approval is rejected by the backend.
2. Approval for one job cannot authorize a different job.
3. Editing a document or answer invalidates approval.
4. Two simultaneous submit requests cannot create duplicate attempts (UniqueConstraint).
5. Rejected and cancelled applications cannot be submitted.
6. Provider timeout after a possible successful submission does not trigger blind resubmission (confirmation_pending).
7. Unsupported providers route to manual handoff with prepared packet.
8. A confirmed provider receipt updates the application status correctly.
9. Audit records identify the actor, action, timestamp, and relevant version IDs.
10. Cross-user access and authorization failures are enforced.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.entities import (
    ApplicationSubmissionAttempt,
    DocumentVersion,
    GeneratedDocument,
    JobApplication,
    JobPosting,
    Profile,
    Skill,
    User,
    WorkflowExecutionLog,
)
from app.services.submission.adapters.base import SubmissionAdapter
from app.services.submission.adapters.registry import submission_registry
from app.services.submission.schemas import (
    ApplicationApprovalReviewRequest,
    ApplicationPackage,
    ApplicationSubmitRequest,
    ProposedFormAnswers,
    ProviderCapabilityInfo,
    SubmissionResult,
)
from app.services.submission.service import (
    BlindResubmissionError,
    DuplicateSubmissionError,
    submission_service,
)
from app.services.workflow.nodes import UnauthorizedSubmissionError


@pytest.fixture
async def test_candidate():
    """Create a verified test candidate with profile and skills."""
    uid = uuid.uuid4().hex[:8]
    email = f"candidate_p7_{uid}@example.com"
    async with async_session_factory() as session:
        user = User(
            email=email,
            hashed_password="hashed_test_password_123",
            full_name=f"Candidate P7 {uid}",
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        profile = Profile(
            user_id=user.id,
            headline="Lead Infrastructure Architect",
            target_job_titles=["Staff Infrastructure Engineer"],
            location="San Francisco, CA",
            remote_preference="hybrid",
            work_authorization_status="citizen",
            profile_version=1,
            phone="+1 555-0199",
            linkedin_url="https://linkedin.com/in/candidate",
            github_url="https://github.com/candidate",
        )
        session.add(profile)
        skill = Skill(
            user_id=user.id,
            name="FastAPI",
            proficiency_level="expert",
            years_experience=5.0,
        )
        session.add(skill)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def test_job_a():
    """Create test Job A."""
    uid = uuid.uuid4().hex[:8]
    async with async_session_factory() as session:
        job = JobPosting(
            source="greenhouse",
            source_id=f"gh-job-a-{uid}",
            canonical_url=f"https://boards.greenhouse.io/acme/jobs/{uid}",
            title="Senior Distributed Systems Engineer",
            company="Acme Corp",
            description="Build scalable distributed services in Python and PostgreSQL.",
            location="Remote",
            work_mode="remote",
            employment_type="full_time",
            retrieved_at=datetime.now(UTC),
            is_active=True,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


@pytest.fixture
async def test_job_b():
    """Create test Job B."""
    uid = uuid.uuid4().hex[:8]
    async with async_session_factory() as session:
        job = JobPosting(
            source="lever",
            source_id=f"lever-job-b-{uid}",
            canonical_url=f"https://jobs.lever.co/beta/{uid}",
            title="Principal Cloud Architect",
            company="Beta Dynamics",
            description="Lead AWS and GCP cloud infrastructure transformations.",
            location="New York, NY",
            work_mode="hybrid",
            employment_type="full_time",
            retrieved_at=datetime.now(UTC),
            is_active=True,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


@pytest.fixture
async def candidate_documents(test_candidate, test_job_a):
    """Create base resume and cover letter versions for test candidate."""
    async with async_session_factory() as session:
        resume_doc = GeneratedDocument(
            user_id=test_candidate.id,
            job_id=test_job_a.id,
            doc_type="resume",
            title="Tailored Resume for Acme Corp",
            template_id="modern",
            candidate_profile_version=1,
        )
        session.add(resume_doc)
        await session.commit()
        await session.refresh(resume_doc)

        res_v1 = DocumentVersion(
            document_id=resume_doc.id,
            version_number=1,
            structured_data={"summary": "Candidate Profile: 10+ years backend engineering..."},
            formatted_text="Candidate Profile: 10+ years engineering backend distributed systems...",
            model_name="mock-model",
            prompt_version="1.0.0",
            validation_report={"fact_verification_score": 0.98},
            is_approved=False,
            change_summary="Initial generation",
        )
        session.add(res_v1)

        cl_doc = GeneratedDocument(
            user_id=test_candidate.id,
            job_id=test_job_a.id,
            doc_type="cover_letter",
            title="Tailored Cover Letter for Acme Corp",
            template_id="modern",
            candidate_profile_version=1,
        )
        session.add(cl_doc)
        await session.commit()
        await session.refresh(cl_doc)

        cl_v1 = DocumentVersion(
            document_id=cl_doc.id,
            version_number=1,
            structured_data={"body": "Dear Hiring Team, I am thrilled to submit my qualifications..."},
            formatted_text="Dear Hiring Team, I am thrilled to submit my qualifications...",
            model_name="mock-model",
            prompt_version="1.0.0",
            validation_report={"fact_verification_score": 0.97},
            is_approved=False,
            change_summary="Initial generation",
        )
        session.add(cl_v1)
        await session.commit()
        return {
            "resume_id": resume_doc.id,
            "resume_version_id": res_v1.id,
            "cover_letter_id": cl_doc.id,
            "cover_letter_version_id": cl_v1.id,
        }


@pytest.fixture
async def sample_application(test_candidate, test_job_a, candidate_documents):
    """Create a sample application in awaiting_approval status."""
    async with async_session_factory() as session:
        app = JobApplication(
            user_id=test_candidate.id,
            job_id=test_job_a.id,
            status="awaiting_approval",
            submission_mode="manual_handoff",
            approval_status="pending",
            idempotency_key=f"idem-{uuid.uuid4().hex}",
            workflow_thread_id=f"thread-{uuid.uuid4().hex[:12]}",
            resume_version_id=candidate_documents["resume_version_id"],
            cover_letter_version_id=candidate_documents["cover_letter_version_id"],
            form_answers={
                "full_name": test_candidate.full_name,
                "email": test_candidate.email,
                "phone": "+1 555-0199",
                "work_authorization": "Authorized to work in US without sponsorship",
                "notice_period": "2 weeks",
            },
        )
        session.add(app)
        await session.commit()
        await session.refresh(app)
        return app


# =====================================================================
# 1. Submission without approval is rejected by the backend
# =====================================================================
@pytest.mark.asyncio
async def test_submission_without_approval_is_rejected(test_candidate, sample_application):
    """Ensure submission cannot occur unless explicit human approval was recorded."""
    async with async_session_factory() as session:
        submit_req = ApplicationSubmitRequest(
            submission_key=f"sub-key-{uuid.uuid4().hex[:8]}",
        )
        with pytest.raises(UnauthorizedSubmissionError) as exc_info:
            await submission_service.submit_application(
                session,
                user_id=test_candidate.id,
                application_id=sample_application.id,
                submit_req=submit_req,
            )
        assert "human approval is not granted" in str(exc_info.value).lower()


# =====================================================================
# 2. Approval for one job cannot authorize a different job
# =====================================================================
@pytest.mark.asyncio
async def test_approval_for_one_job_cannot_authorize_different_job(
    test_candidate, test_job_b, sample_application
):
    """Ensure an approval snapshot containing Job A cannot authorize Job B."""
    async with async_session_factory() as session:
        # Case A: Approval attempt with wrong job_id is rejected immediately
        approval_req_wrong_job = ApplicationApprovalReviewRequest(
            approved=True,
            job_id=test_job_b.id,
            notes="Malicious approval attempt for wrong job",
        )
        with pytest.raises(ValueError) as exc_info:
            await submission_service.record_human_approval(
                session,
                user_id=test_candidate.id,
                application_id=sample_application.id,
                approval_req=approval_req_wrong_job,
            )
        assert "job mismatch" in str(exc_info.value).lower()

        # Case B: Approved for Job A, client attempts to submit for Job B
        pkg = await submission_service.prepare_package(session, test_candidate.id, sample_application.id)
        valid_approval = ApplicationApprovalReviewRequest(
            approved=True,
            job_id=sample_application.job_id,
            expected_package_hash=pkg.package_hash,
            notes="Valid approval for Job A",
        )
        await submission_service.record_human_approval(
            session,
            user_id=test_candidate.id,
            application_id=sample_application.id,
            approval_req=valid_approval,
        )

        submit_req_wrong_job = ApplicationSubmitRequest(
            submission_key=f"sub-key-{uuid.uuid4().hex[:8]}",
            target_job_id=test_job_b.id,
        )
        with pytest.raises(UnauthorizedSubmissionError) as exc_info2:
            await submission_service.submit_application(
                session,
                user_id=test_candidate.id,
                application_id=sample_application.id,
                submit_req=submit_req_wrong_job,
            )
        assert "job authorization mismatch" in str(exc_info2.value).lower()


# =====================================================================
# 3. Editing a document or answer invalidates approval
# =====================================================================
@pytest.mark.asyncio
async def test_editing_document_or_answer_invalidates_approval(
    test_candidate, sample_application
):
    """Modifying form answers or document version must invalidate approval."""
    async with async_session_factory() as session:
        # 1. Prepare and approve package
        pkg = await submission_service.prepare_package(session, test_candidate.id, sample_application.id)
        await submission_service.record_human_approval(
            session,
            user_id=test_candidate.id,
            application_id=sample_application.id,
            approval_req=ApplicationApprovalReviewRequest(
                approved=True,
                expected_package_hash=pkg.package_hash,
            ),
        )

        # Verify it is currently approved
        refreshed_pkg = await submission_service.prepare_package(session, test_candidate.id, sample_application.id)
        assert refreshed_pkg.approval_status == "approved"
        assert not refreshed_pkg.is_content_altered_since_approval

        # 2. Candidate modifies proposed answers (e.g. changes notice period)
        updated_answers = ProposedFormAnswers(
            full_name=test_candidate.full_name,
            email=test_candidate.email,
            phone="+1 555-0199",
            notice_period="Immediate / 0 days",
        )
        await submission_service.update_form_answers(
            session,
            user_id=test_candidate.id,
            application_id=sample_application.id,
            answers=updated_answers,
        )

        # 3. Package must now reflect invalidated status
        post_edit_pkg = await submission_service.prepare_package(session, test_candidate.id, sample_application.id)
        assert post_edit_pkg.approval_status == "invalidated"
        assert post_edit_pkg.is_content_altered_since_approval

        # 4. Attempting submission without fresh approval must fail
        with pytest.raises(UnauthorizedSubmissionError):
            await submission_service.submit_application(
                session,
                user_id=test_candidate.id,
                application_id=sample_application.id,
                submit_req=ApplicationSubmitRequest(
                    submission_key=f"sub-key-{uuid.uuid4().hex[:8]}"
                ),
            )

        # 5. Re-approving the package with new hash allows submission
        await submission_service.record_human_approval(
            session,
            user_id=test_candidate.id,
            application_id=sample_application.id,
            approval_req=ApplicationApprovalReviewRequest(
                approved=True,
                expected_package_hash=post_edit_pkg.package_hash,
                notes="Re-approved after updating notice period",
            ),
        )
        reapproved_pkg = await submission_service.prepare_package(session, test_candidate.id, sample_application.id)
        assert reapproved_pkg.approval_status == "approved"
        assert not reapproved_pkg.is_content_altered_since_approval


# =====================================================================
# 4. Simultaneous submit requests cannot create duplicate attempts
# =====================================================================
@pytest.mark.asyncio
async def test_duplicate_submission_key_rejected_by_db_constraint(
    test_candidate, sample_application
):
    """Enforce idempotency: two submit calls with the same submission_key are blocked."""
    async with async_session_factory() as session:
        pkg = await submission_service.prepare_package(session, test_candidate.id, sample_application.id)
        await submission_service.record_human_approval(
            session,
            user_id=test_candidate.id,
            application_id=sample_application.id,
            approval_req=ApplicationApprovalReviewRequest(
                approved=True,
                expected_package_hash=pkg.package_hash,
            ),
        )

        submission_key = f"idempotent-submit-{uuid.uuid4().hex}"

        # First submit succeeds
        result1 = await submission_service.submit_application(
            session,
            user_id=test_candidate.id,
            application_id=sample_application.id,
            submit_req=ApplicationSubmitRequest(submission_key=submission_key),
        )
        assert result1.status in ("manual_handoff", "submitted")

        # Second simultaneous submit with the EXACT same submission_key must raise DuplicateSubmissionError
        with pytest.raises(DuplicateSubmissionError):
            await submission_service.submit_application(
                session,
                user_id=test_candidate.id,
                application_id=sample_application.id,
                submit_req=ApplicationSubmitRequest(submission_key=submission_key),
            )


# =====================================================================
# 5. Rejected and cancelled applications cannot be submitted
# =====================================================================
@pytest.mark.asyncio
async def test_rejected_and_cancelled_applications_cannot_be_submitted(
    test_candidate, sample_application
):
    """Verify that applications marked rejected or cancelled refuse submission."""
    async with async_session_factory() as session:
        # Candidate rejects package
        await submission_service.record_human_approval(
            session,
            user_id=test_candidate.id,
            application_id=sample_application.id,
            approval_req=ApplicationApprovalReviewRequest(
                approved=False,
                notes="Compensation does not match expectations",
            ),
        )

        with pytest.raises(UnauthorizedSubmissionError) as exc_info:
            await submission_service.submit_application(
                session,
                user_id=test_candidate.id,
                application_id=sample_application.id,
                submit_req=ApplicationSubmitRequest(
                    submission_key=f"sub-{uuid.uuid4().hex[:8]}"
                ),
            )
        assert "cannot submit an application with status 'rejected'" in str(exc_info.value).lower()

        # Candidate cancels application
        app = await session.get(JobApplication, sample_application.id)
        app.status = "cancelled"
        await session.commit()

        with pytest.raises(UnauthorizedSubmissionError) as exc_info2:
            await submission_service.submit_application(
                session,
                user_id=test_candidate.id,
                application_id=sample_application.id,
                submit_req=ApplicationSubmitRequest(
                    submission_key=f"sub-{uuid.uuid4().hex[:8]}"
                ),
            )
        assert "cannot submit an application with status 'cancelled'" in str(exc_info2.value).lower()


# =====================================================================
# 6. Provider timeout does not trigger blind resubmission
# =====================================================================
class SimulatingTimeoutAdapter(SubmissionAdapter):
    """Adapter simulating an external network/API timeout after dispatch."""

    def provider_id(self) -> str:
        return "simulated_timeout"

    def capabilities(self, context: dict[str, Any]) -> ProviderCapabilityInfo:
        return ProviderCapabilityInfo(
            provider_id="simulated_timeout",
            provider_name="Timeout Test Provider",
            is_direct_api=True,
            supports_submission=True,
            requires_credentials=False,
            has_credentials=True,
            submission_method="automated_api",
        )

    async def submit(
        self, package: ApplicationPackage, submission_key: str, context: dict[str, Any]
    ) -> SubmissionResult:
        return SubmissionResult(
            status="confirmation_pending",
            error_message="Gateway timeout waiting for provider receipt. Blind resubmission prevented.",
            blind_resubmission_prevented=True,
            response_payload={"error": "ReadTimeout after HTTP POST /applications"},
        )


@pytest.mark.asyncio
async def test_provider_timeout_does_not_trigger_blind_resubmission(
    test_candidate, sample_application
):
    """Provider timeout sets confirmation_pending and prevents blind resubmissions."""
    timeout_adapter = SimulatingTimeoutAdapter()
    submission_registry.register_adapter("simulated_timeout", timeout_adapter)

    async with async_session_factory() as session:
        app = await session.get(JobApplication, sample_application.id)
        job = await session.get(JobPosting, app.job_id)
        job.source = "simulated_timeout"
        await session.commit()

        pkg = await submission_service.prepare_package(session, test_candidate.id, sample_application.id)
        await submission_service.record_human_approval(
            session,
            user_id=test_candidate.id,
            application_id=sample_application.id,
            approval_req=ApplicationApprovalReviewRequest(
                approved=True,
                expected_package_hash=pkg.package_hash,
            ),
        )

        sub_key = f"timeout-test-{uuid.uuid4().hex[:8]}"
        res = await submission_service.submit_application(
            session,
            user_id=test_candidate.id,
            application_id=sample_application.id,
            submit_req=ApplicationSubmitRequest(submission_key=sub_key),
        )

        # 1. Result must be confirmation_pending, NOT submitted
        assert res.status == "confirmation_pending"
        assert res.blind_resubmission_prevented is True

        # 2. Database application status must be confirmation_pending
        await session.refresh(app)
        assert app.status == "confirmation_pending"

        # 3. Subsequent submit attempt is safely guarded
        with pytest.raises(BlindResubmissionError) as exc_info:
            await submission_service.submit_application(
                session,
                user_id=test_candidate.id,
                application_id=sample_application.id,
                submit_req=ApplicationSubmitRequest(
                    submission_key=f"retry-{uuid.uuid4().hex[:8]}"
                ),
            )
        assert "blind resubmissions are blocked" in str(exc_info.value).lower()


# =====================================================================
# 7. Unsupported providers route to manual handoff
# =====================================================================
@pytest.mark.asyncio
async def test_unsupported_providers_route_to_manual_handoff(
    test_candidate, sample_application
):
    """Unsupported sites produce complete manual handoff packet with labeled answers."""
    async with async_session_factory() as session:
        app = await session.get(JobApplication, sample_application.id)
        job = await session.get(JobPosting, app.job_id)
        job.source = "unsupported_portal"
        await session.commit()

        pkg = await submission_service.prepare_package(session, test_candidate.id, sample_application.id)
        await submission_service.record_human_approval(
            session,
            user_id=test_candidate.id,
            application_id=sample_application.id,
            approval_req=ApplicationApprovalReviewRequest(
                approved=True,
                expected_package_hash=pkg.package_hash,
            ),
        )

        res = await submission_service.submit_application(
            session,
            user_id=test_candidate.id,
            application_id=sample_application.id,
            submit_req=ApplicationSubmitRequest(
                submission_key=f"handoff-sub-{uuid.uuid4().hex[:8]}"
            ),
        )

        assert res.status == "manual_handoff"
        assert res.handoff_packet is not None

        packet = res.handoff_packet
        assert packet.original_application_url == job.canonical_url
        assert len(packet.labeled_answers) >= 3
        # Ensure sensitive questions notice is present
        assert any(a.is_sensitive for a in packet.labeled_answers)
        assert any("CAPTCHA" in inst for inst in packet.instructions)
        assert any(a.field_key == "full_name" for a in packet.labeled_answers)



# =====================================================================
# 8. Confirmed provider receipt updates the application status correctly
# =====================================================================
class SimulatingConfirmedAdapter(SubmissionAdapter):
    """Adapter simulating a verified employer integration with confirmed receipt."""

    def provider_id(self) -> str:
        return "simulated_confirmed"

    def capabilities(self, context: dict[str, Any]) -> ProviderCapabilityInfo:
        return ProviderCapabilityInfo(
            provider_id="simulated_confirmed",
            provider_name="Confirmed Integration Test Provider",
            is_direct_api=True,
            supports_submission=True,
            requires_credentials=False,
            has_credentials=True,
            submission_method="automated_api",
        )

    async def submit(
        self, package: ApplicationPackage, submission_key: str, context: dict[str, Any]
    ) -> SubmissionResult:
        return SubmissionResult(
            status="submitted",
            receipt_reference="CONF-RECEIPT-889922",
            response_payload={
                "id": 998811,
                "created_at": datetime.now(UTC).isoformat(),
                "status": "applied",
            },
        )


@pytest.mark.asyncio
async def test_confirmed_provider_receipt_updates_status(
    test_candidate, sample_application
):
    """Credible receipt updates application status to 'submitted' and persists receipt."""
    confirmed_adapter = SimulatingConfirmedAdapter()
    submission_registry.register_adapter("simulated_confirmed", confirmed_adapter)

    async with async_session_factory() as session:
        app = await session.get(JobApplication, sample_application.id)
        job = await session.get(JobPosting, app.job_id)
        job.source = "simulated_confirmed"
        await session.commit()

        pkg = await submission_service.prepare_package(session, test_candidate.id, sample_application.id)
        await submission_service.record_human_approval(
            session,
            user_id=test_candidate.id,
            application_id=sample_application.id,
            approval_req=ApplicationApprovalReviewRequest(
                approved=True,
                expected_package_hash=pkg.package_hash,
            ),
        )

        sub_key = f"confirmed-sub-{uuid.uuid4().hex[:8]}"
        res = await submission_service.submit_application(
            session,
            user_id=test_candidate.id,
            application_id=sample_application.id,
            submit_req=ApplicationSubmitRequest(submission_key=sub_key),
        )

        assert res.status == "submitted"
        assert res.receipt_reference == "CONF-RECEIPT-889922"

        # Verify database record
        await session.refresh(app)
        assert app.status == "submitted"
        assert app.tracking_metadata is not None
        assert app.tracking_metadata.get("confirmation_reference") == "CONF-RECEIPT-889922"


# =====================================================================
# 9. Audit records identify actor, action, timestamp, and version IDs
# =====================================================================
@pytest.mark.asyncio
async def test_audit_records_captured_on_every_attempt(
    test_candidate, sample_application
):
    """Audit attempts and workflow logs record actor, timestamp, and document versions."""
    async with async_session_factory() as session:
        pkg = await submission_service.prepare_package(session, test_candidate.id, sample_application.id)
        await submission_service.record_human_approval(
            session,
            user_id=test_candidate.id,
            application_id=sample_application.id,
            approval_req=ApplicationApprovalReviewRequest(
                approved=True,
                expected_package_hash=pkg.package_hash,
                notes="Audit trail test approval",
            ),
        )

        sub_key = f"audit-test-key-{uuid.uuid4().hex[:8]}"
        await submission_service.submit_application(
            session,
            user_id=test_candidate.id,
            application_id=sample_application.id,
            submit_req=ApplicationSubmitRequest(submission_key=sub_key),
        )

        # Query ApplicationSubmissionAttempt table
        stmt = select(ApplicationSubmissionAttempt).where(
            ApplicationSubmissionAttempt.application_id == sample_application.id
        )
        attempts = (await session.execute(stmt)).scalars().all()
        assert len(attempts) >= 1
        latest_attempt = attempts[-1]
        assert latest_attempt.user_id == test_candidate.id
        assert latest_attempt.submission_key == sub_key
        assert latest_attempt.started_at is not None
        assert latest_attempt.package_hash == pkg.package_hash
        assert latest_attempt.resume_version_id == sample_application.resume_version_id
        assert latest_attempt.cover_letter_version_id == sample_application.cover_letter_version_id

        # Query WorkflowExecutionLog table
        log_stmt = select(WorkflowExecutionLog).where(
            WorkflowExecutionLog.application_id == sample_application.id
        )
        logs = (await session.execute(log_stmt)).scalars().all()
        assert any(entry.node_name == "human_review_approval" for entry in logs)
        assert any(entry.node_name == "application_submission" for entry in logs)


# =====================================================================
# 10. Cross-user access and authorization failures
# =====================================================================
@pytest.mark.asyncio
async def test_cross_user_access_rejected_via_api(
    async_client: AsyncClient, sample_application
):
    """Ensure User 2 cannot inspect, edit answers, approve, or submit User 1's application."""
    # Register User 2
    u2_reg = {
        "email": f"u2_{uuid.uuid4().hex[:8]}@example.com",
        "password": "Password123!Secure",
        "full_name": "User Two",
    }
    resp2 = await async_client.post("/api/v1/auth/register", json=u2_reg)
    token2 = resp2.json()["token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    target_app_id = sample_application.id

    # User 2 attempts to GET package owned by test_candidate
    get_res = await async_client.get(f"/api/v1/applications/{target_app_id}/package", headers=headers2)
    assert get_res.status_code in (403, 404)

    # User 2 attempts to PUT answers
    put_res = await async_client.put(
        f"/api/v1/applications/{target_app_id}/answers",
        json={
            "form_answers": {
                "full_name": "Attacker",
                "email": "attacker@example.com",
            }
        },
        headers=headers2,
    )
    assert put_res.status_code in (403, 404)

    # User 2 attempts to approve User 1's application
    approve_res = await async_client.post(
        f"/api/v1/applications/{target_app_id}/review-approval",
        json={"approved": True, "notes": "Hacked approval"},
        headers=headers2,
    )
    assert approve_res.status_code in (403, 404)

    # User 2 attempts to submit User 1's application
    sub_res = await async_client.post(
        f"/api/v1/applications/{target_app_id}/submit",
        json={"submission_key": "cross-user-sub-key"},
        headers=headers2,
    )
    assert sub_res.status_code in (403, 404)

    # User 2 attempts to view submission attempts
    att_res = await async_client.get(
        f"/api/v1/applications/{target_app_id}/attempts", headers=headers2
    )
    assert att_res.status_code in (403, 404)
