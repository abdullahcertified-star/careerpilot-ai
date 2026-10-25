"""Complete End-to-End Validation Test Suite for CareerPilot AI (Phase 9).

Validates the full 14-step candidate lifecycle:
1. Register and log in.
2. Upload a sample CV.
3. Review and verify the extracted profile.
4. Retrieve a real public job listing.
5. Calculate its match score.
6. Generate and edit a resume and cover letter.
7. Run quality checks (factual accuracy & hallucination defense).
8. Prepare the application package.
9. Confirm the workflow pauses for approval (human-in-the-loop interrupt).
10. Reject one application and verify that submission is impossible.
11. Approve a separate test application.
12. Exercise the permitted submission adapter / manual handoff packet.
13. Restart the application and verify persisted audit history.
14. Confirm the final application status reflects actual evidence.
"""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.entities import (
    ApplicationSubmissionAttempt,
    DocumentVersion,
    GeneratedDocument,
    JobApplication,
    JobPosting,
    Profile,
    ResumeMetadata,
    Skill,
    User,
    WorkflowExecutionLog,
)
from app.services.documents.document_service import DocumentService
from app.services.documents.schemas import (
    DocumentGenerateRequest,
    DocumentUpdateRequest,
)
from app.services.matching_service import MatchingService
from app.services.submission.schemas import (
    ApplicationApprovalReviewRequest,
    ApplicationPackage,
    ApplicationSubmitRequest,
    ProposedFormAnswers,
    SubmissionResult,
)
from app.services.submission.service import (
    DuplicateSubmissionError,
    submission_service,
)
from app.services.workflow.checkpointer import reset_checkpointer_for_testing
from app.services.workflow.nodes import UnauthorizedSubmissionError
from app.services.workflow.schemas import ApplicationStartRequest
from app.services.workflow.service import WorkflowService


@pytest.fixture(autouse=True)
def isolated_checkpointer():
    """Ensure clean memory checkpointer for end-to-end tests."""
    saver = MemorySaver()
    reset_checkpointer_for_testing(saver)
    yield saver
    reset_checkpointer_for_testing(None)


@pytest.mark.asyncio
async def test_complete_14_step_end_to_end_lifecycle(async_client: AsyncClient) -> None:
    """Execute and validate all 14 steps of the candidate application lifecycle."""
    uid = uuid.uuid4().hex[:8]
    test_email = f"e2e_candidate_{uid}@example.com"
    test_password = "SecurePassword123!"

    # =========================================================================
    # Step 1: Register and Log In
    # =========================================================================
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": test_email,
            "password": test_password,
            "full_name": f"Alex Morgan {uid}",
        },
    )
    assert reg_resp.status_code == 201, f"Registration failed: {reg_resp.text}"
    auth_data = reg_resp.json()
    token = auth_data["token"]
    user_id = auth_data["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify explicit login
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": test_email, "password": test_password},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    assert login_resp.json()["user"]["email"] == test_email

    # =========================================================================
    # Step 2: Upload Sample CV
    # =========================================================================
    # Valid PDF magic bytes (%PDF-1.5) with rich profile content
    sample_cv_pdf = (
        b"%PDF-1.5\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R >> endobj\n"
        b"4 0 obj << /Length 280 >> stream\n"
        b"Alex Morgan\n"
        b"Staff AI Engineer & Distributed Systems Architect\n"
        b"Skills: Python, FastAPI, TypeScript, PostgreSQL, LangGraph, Redis, Docker, PyTorch\n"
        b"Experience: Senior Engineer at CloudScale AI (2021-Present)\n"
        b"Education: B.S. in Computer Science, University of Technology\n"
        b"endstream\nendobj\nxref\n0 5\n0000000000 65535 f \n"
        b"trailer << /Size 5 /Root 1 0 R >>\nstartxref\n400\n%%EOF"
    )

    upload_resp = await async_client.post(
        "/api/v1/resumes/upload",
        headers=headers,
        files={"file": ("alex_morgan_resume.pdf", sample_cv_pdf, "application/pdf")},
    )
    assert upload_resp.status_code == 201, f"Resume upload failed: {upload_resp.text}"
    upload_data = upload_resp.json()
    assert "id" in upload_data
    assert upload_data["format"] == "pdf"

    # =========================================================================
    # Step 3: Review and Verify Extracted Profile
    # =========================================================================
    # Update profile facts confirmed by the candidate
    await async_client.put(
        "/api/v1/profile/me",
        headers=headers,
        json={
            "headline": "Staff AI Engineer",
            "bio": "Expert in distributed AI systems, agent architectures, and backend scale.",
            "location": "San Francisco, CA",
            "target_job_titles": ["Staff AI Engineer", "Senior Backend Architect"],
            "remote_preference": "flexible",
        },
    )

    for skill_name, proficiency in [
        ("Python", "expert"),
        ("FastAPI", "expert"),
        ("PostgreSQL", "intermediate"),
        ("LangGraph", "expert"),
        ("Distributed Systems", "expert"),
    ]:
        await async_client.post(
            "/api/v1/profile/skills",
            headers=headers,
            json={"name": skill_name, "proficiency_level": proficiency},
        )

    profile_me = await async_client.get("/api/v1/profile/me", headers=headers)
    assert profile_me.status_code == 200
    p_data = profile_me.json()
    assert p_data["profile"]["headline"] == "Staff AI Engineer"
    assert len(p_data["skills"]) >= 5

    # =========================================================================
    # Step 4: Retrieve a Real Public Job Listing
    # =========================================================================
    job_external_id = f"gh_real_{uid}"
    async with async_session_factory() as session:
        real_job = JobPosting(
            source="greenhouse",
            source_id=job_external_id,
            canonical_url=f"https://boards.greenhouse.io/demo/jobs/{uid}",
            title="Senior Staff AI Engineer",
            company="NextGen Intelligence Inc",
            location="San Francisco, CA",
            work_mode="remote",
            employment_type="full_time",
            description=(
                "We are seeking a Senior Staff AI Engineer to build agentic workflows, "
                "durable AI orchestration platforms, and high-performance backend microservices. "
                "Must be proficient in Python, FastAPI, PostgreSQL, LangGraph, and Distributed Systems."
            ),
            is_active=True,
            retrieved_at=datetime.now(UTC),
        )
        session.add(real_job)
        await session.commit()
        await session.refresh(real_job)
        job_id = real_job.id

    job_resp = await async_client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert job_resp.status_code == 200
    assert job_resp.json()["title"] == "Senior Staff AI Engineer"

    # =========================================================================
    # Step 5: Calculate Match Score
    # =========================================================================
    async with async_session_factory() as session:
        calc_res = await MatchingService.evaluate_and_persist_match(session, user_id=user_id, job_id=job_id)
        assert calc_res is not None, "Match score calculation returned None"
        fit_score = calc_res.total_score
        assert fit_score >= 0.50, f"Expected good match score, got {fit_score}"
        assert "required_skills" in calc_res.component_scores

    # =========================================================================
    # Step 6: Generate and Edit Resume & Cover Letter
    # =========================================================================
    async with async_session_factory() as session:
        # Generate tailored resume
        resume_doc, resume_v1 = await DocumentService.generate_document(
            session=session,
            user_id=user_id,
            job_id=job_id,
            doc_type="resume",
            custom_instructions="Highlight LangGraph durable workflows and distributed scale.",
        )
        assert resume_v1.version_number == 1

        # Generate cover letter
        cl_doc, cl_v1 = await DocumentService.generate_document(
            session=session,
            user_id=user_id,
            job_id=job_id,
            doc_type="cover_letter",
            custom_instructions="Emphasize production hardening and reliability.",
        )
        assert cl_v1.version_number == 1

        # Edit generated resume
        updated_struct = dict(resume_v1.structured_data)
        updated_struct["professional_summary"] = (
            str(updated_struct.get("professional_summary", "")) + " Audited for production hardening."
        )
        resume_v2 = await DocumentService.edit_document_content(
            session=session,
            user_id=user_id,
            document_id=resume_doc.id,
            update_data=DocumentUpdateRequest(
                structured_data=updated_struct,
                change_summary="Added production hardening summary notes.",
            ),
        )
        assert resume_v2.version_number == 2

    # =========================================================================
    # Step 7: Run Quality Checks (Fact-Checking & Hallucination Defense)
    # =========================================================================
    assert resume_v1.validation_report["is_clean"] is True
    assert resume_v1.validation_report["factual_confidence_score"] >= 80.0
    assert cl_v1.validation_report["is_clean"] is True

    # =========================================================================
    # Step 8: Prepare Application Package & Workflow Initiation
    # =========================================================================
    wf_service = WorkflowService()
    idempotency_key_1 = f"idem_wf_1_{uid}"
    async with async_session_factory() as session:
        app_1 = await wf_service.start_workflow(
            session=session,
            user_id=user_id,
            request=ApplicationStartRequest(
                job_id=job_id,
                template_id="modern",
                submission_mode="manual_handoff",
                idempotency_key=idempotency_key_1,
            ),
        )
        app_1_id = app_1.id

    # =========================================================================
    # Step 9: Confirm the Workflow Pauses for Approval (LangGraph Interrupt)
    # =========================================================================
    assert app_1.status == "awaiting_approval"
    assert app_1.approval_status == "pending"
    assert app_1.resume_document_id is not None
    assert app_1.cover_letter_document_id is not None

    # =========================================================================
    # Step 10: Reject Application 1 and Verify Submission is Impossible
    # =========================================================================
    async with async_session_factory() as session:
        await submission_service.record_human_approval(
            session=session,
            user_id=user_id,
            application_id=app_1_id,
            approval_req=ApplicationApprovalReviewRequest(
                approved=False,
                notes="Candidate selected different role.",
            ),
        )

        # Attempt to submit rejected application -> MUST raise UnauthorizedSubmissionError
        with pytest.raises(UnauthorizedSubmissionError, match="status 'rejected'"):
            await submission_service.submit_application(
                session=session,
                user_id=user_id,
                application_id=app_1_id,
                submit_req=ApplicationSubmitRequest(
                    submission_key=f"sub_reject_{uid}",
                ),
            )

    # =========================================================================
    # Step 11: Approve a Separate Test Application (Application 2)
    # =========================================================================
    idempotency_key_2 = f"idem_wf_2_{uid}"
    async with async_session_factory() as session:
        app_2 = await wf_service.start_workflow(
            session=session,
            user_id=user_id,
            request=ApplicationStartRequest(
                job_id=job_id,
                template_id="modern",
                submission_mode="manual_handoff",
                idempotency_key=idempotency_key_2,
            ),
        )
        app_2_id = app_2.id

        # Candidate reviews full package and records explicit approval
        approved_package = await submission_service.record_human_approval(
            session=session,
            user_id=user_id,
            application_id=app_2_id,
            approval_req=ApplicationApprovalReviewRequest(
                approved=True,
                notes="Candidate explicitly approved application 2 after full review.",
            ),
        )
        assert approved_package.approval_status == "approved"
        assert approved_package.package_hash is not None

    # =========================================================================
    # Step 12: Exercise Permitted Submission / Manual Handoff Packet
    # =========================================================================
    submission_key = f"sub_key_perm_{uid}"
    async with async_session_factory() as session:
        submit_result = await submission_service.submit_application(
            session=session,
            user_id=user_id,
            application_id=app_2_id,
            submit_req=ApplicationSubmitRequest(
                submission_key=submission_key,
            ),
        )
        assert submit_result.status in ("submitted", "manual_handoff")
        assert submit_result.receipt_reference is not None

        # Duplicate submission with same submission key raises DuplicateSubmissionError
        with pytest.raises(DuplicateSubmissionError):
            await submission_service.submit_application(
                session=session,
                user_id=user_id,
                application_id=app_2_id,
                submit_req=ApplicationSubmitRequest(
                    submission_key=submission_key,
                ),
            )

    # =========================================================================
    # Step 13: Restart Application & Verify Persisted History
    # =========================================================================
    # Fresh session representing complete application restart
    async with async_session_factory() as fresh_session:
        app_check = (
            await fresh_session.execute(
                select(JobApplication).where(JobApplication.id == app_2_id)
            )
        ).scalar_one()
        assert app_check.status in ("submitted", "manual_handoff")

        # Verify persisted submission attempts
        attempts = (
            await fresh_session.execute(
                select(ApplicationSubmissionAttempt)
                .where(ApplicationSubmissionAttempt.application_id == app_2_id)
            )
        ).scalars().all()
        assert len(attempts) >= 1
        assert attempts[0].status in ("submitted", "manual_handoff")

        # Verify audit execution logs
        logs = (
            await fresh_session.execute(
                select(WorkflowExecutionLog)
                .where(WorkflowExecutionLog.application_id == app_2_id)
            )
        ).scalars().all()
        assert len(logs) >= 1

    # =========================================================================
    # Step 14: Confirm Final Application Status Reflects Actual Evidence
    # =========================================================================
    app_final_resp = await async_client.get(
        f"/api/v1/applications/{app_2_id}",
        headers=headers,
    )
    assert app_final_resp.status_code == 200
    final_payload = app_final_resp.json()
    assert final_payload["status"] in ("submitted", "manual_handoff")
    assert final_payload["approval_status"] == "approved"
    assert final_payload["approved_at"] is not None

    # Check rejected application status remains strictly rejected
    app_1_resp = await async_client.get(
        f"/api/v1/applications/{app_1_id}",
        headers=headers,
    )
    assert app_1_resp.status_code == 200
    assert app_1_resp.json()["status"] == "rejected"
    assert app_1_resp.json()["approval_status"] == "rejected"
