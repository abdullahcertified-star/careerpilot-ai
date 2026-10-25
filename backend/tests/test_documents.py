"""Comprehensive test suite for Phase 5: Resume and Cover Letter generation,
factual consistency verification, version history immutability, document exports,
and cross-user authorization barriers.
"""

import io
import pytest
from docx import Document as DocxReader
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import select

from app.core.database import get_db
from app.models.entities import (
    DocumentVersion,
    Education,
    Experience,
    GeneratedDocument,
    JobPosting,
    Profile,
    Skill,
    User,
)
from app.services.documents.docx_renderer import docx_renderer
from app.services.documents.factual_checker import factual_checker
from app.services.documents.pdf_renderer import pdf_renderer
from app.services.documents.resume_agent import MissingAIConfigurationError, resume_agent
from app.services.documents.schemas import (
    ResumeEducationItem,
    ResumeExperienceItem,
    StructuredCoverLetter,
    StructuredResume,
)


@pytest.fixture
async def auth_headers(async_client: AsyncClient):
    """Registers and authenticates candidate user for documents tests."""
    reg_payload = {
        "email": "candidate.docs@example.com",
        "password": "Password123!Secure",
        "full_name": "Document Candidate",
    }
    resp = await async_client.post("/api/v1/auth/register", json=reg_payload)
    if resp.status_code != 201:
        login_resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": reg_payload["email"], "password": reg_payload["password"]},
        )
        token = login_resp.json()["token"]
    else:
        token = resp.json()["token"]

    return {"Authorization": f"Bearer {token}"}


def create_verified_candidate(
    full_name="Alex Morgan",
    skills=None,
    experiences=None,
    educations=None,
) -> User:
    """Helper creating candidate User with verified background facts."""
    user = User(
        id=55,
        email="alex.morgan@test.com",
        full_name=full_name,
        hashed_password="pw",
    )
    user.profile = Profile(
        user_id=55,
        headline="Senior Full Stack Engineer",
        location="Austin, TX",
        phone="+1 512 555 0199",
        profile_version=2,
    )
    # Skills
    s_names = skills if skills is not None else ["python", "fastapi", "postgresql", "docker"]
    user.skills = [
        Skill(id=i + 1, user_id=55, name=name, proficiency_level="advanced", years_experience=4.0)
        for i, name in enumerate(s_names)
    ]
    # Experiences
    if experiences is None:
        user.experiences = [
            Experience(
                id=1,
                user_id=55,
                company="Stripe",
                title="Software Engineer",
                start_date="2021-01-01",
                end_date="2023-12-31",
                is_current=False,
                description="Built high-throughput payment APIs and event microservices.",
            )
        ]
    else:
        user.experiences = experiences

    # Educations
    if educations is None:
        user.educations = [
            Education(
                id=1,
                user_id=55,
                institution="University of Texas",
                degree="Bachelor of Science",
                field_of_study="Computer Science",
            )
        ]
    else:
        user.educations = educations

    user.certifications = []
    user.projects = []
    return user


def create_test_job(
    title="Staff Backend Engineer",
    company="Datadog",
    description="Seeking a Staff Backend Engineer proficient in Python, PostgreSQL, and distributed systems.",
) -> JobPosting:
    """Helper creating a test job posting."""
    return JobPosting(
        id=77,
        source="greenhouse",
        source_id="gh-datadog-77",
        canonical_url="https://example.com/jobs/datadog-77",
        title=title,
        company=company,
        description=description,
        location="Remote",
        work_mode="remote",
        employment_type="full_time",
    )


# -----------------------------------------------------------------------------
# Unit Tests: Factual Consistency Checker & Anti-Fabrication Guarantees
# -----------------------------------------------------------------------------

def test_unsupported_candidate_claims_are_detected_and_flagged() -> None:
    """Verifies that hallucinated employers, unearned skills, and false degrees are caught."""
    candidate = create_verified_candidate()

    # Create resume with fabricated/unsupported facts
    hallucinated_resume = StructuredResume(
        full_name="Alex Morgan",
        email="alex.morgan@test.com",
        target_title="Staff Backend Engineer",
        target_company="Datadog",
        professional_summary="Senior developer with extensive background.",
        highlighted_skills=["python", "quantum_computing", "rust"],  # quantum_computing & rust unverified
        experience=[
            ResumeExperienceItem(
                company="NASA Jet Propulsion Lab",  # Fake employer!
                title="Lead Astronautical Architect",
                start_date="2018",
                end_date="2021",
                bullets=["Engineered Mars Rover flight software."],
            )
        ],
        education=[
            ResumeEducationItem(
                institution="Harvard University",  # Fake university!
                degree="Doctor of Philosophy",
                field_of_study="Theoretical Physics",
            )
        ],
    )

    report = factual_checker.verify_resume(hallucinated_resume, candidate)

    assert report.is_clean is False
    assert report.factual_confidence_score < 50.0

    flagged_fields = [c.field for c in report.unsupported_claims]
    assert "experience.company" in flagged_fields
    assert "education.institution" in flagged_fields
    assert "highlighted_skills" in flagged_fields

    flagged_claims = [c.claim for c in report.unsupported_claims]
    assert "NASA Jet Propulsion Lab" in flagged_claims
    assert "Harvard University" in flagged_claims
    assert "quantum_computing" in flagged_claims


def test_dates_and_qualifications_remain_consistent_with_verified_facts() -> None:
    """Verifies tenure dates that diverge from verified records are flagged."""
    candidate = create_verified_candidate()

    # Candidate was at Stripe 2021-2023. Resume claims 2012-2024 (exaggeration).
    divergent_resume = StructuredResume(
        full_name="Alex Morgan",
        email="alex.morgan@test.com",
        target_title="Senior Engineer",
        target_company="Datadog",
        professional_summary="Engineer.",
        highlighted_skills=["python", "postgresql"],
        experience=[
            ResumeExperienceItem(
                company="Stripe",
                title="Software Engineer",
                start_date="2012",
                end_date="2024",
                bullets=["API development."],
            )
        ],
        education=[
            ResumeEducationItem(
                institution="University of Texas",
                degree="Bachelor of Science",
                field_of_study="Computer Science",
            )
        ],
    )

    report = factual_checker.verify_resume(divergent_resume, candidate)
    date_flags = [c for c in report.unsupported_claims if c.field == "experience.dates"]
    assert len(date_flags) > 0
    assert "conflict with verified record" in date_flags[0].reason


def test_clean_grounded_resume_passes_validation() -> None:
    """Verifies that an authentic fact-grounded resume receives 100% confidence and is_clean=True."""
    candidate = create_verified_candidate()
    clean_resume = StructuredResume(
        full_name="Alex Morgan",
        email="alex.morgan@test.com",
        target_title="Backend Engineer",
        target_company="Datadog",
        professional_summary="Accomplished engineer targeting Datadog.",
        highlighted_skills=["python", "postgresql"],
        experience=[
            ResumeExperienceItem(
                company="Stripe",
                title="Software Engineer",
                start_date="2021",
                end_date="2023",
                bullets=["Built high-throughput payment APIs."],
            )
        ],
        education=[
            ResumeEducationItem(
                institution="University of Texas",
                degree="Bachelor of Science",
                field_of_study="Computer Science",
            )
        ],
    )

    report = factual_checker.verify_resume(clean_resume, candidate)
    assert report.is_clean is True
    assert report.factual_confidence_score == 100.0
    assert len(report.unsupported_claims) == 0


# -----------------------------------------------------------------------------
# Unit Tests: Document Generation & Export Integrity (DOCX and PDF)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generated_documents_include_correct_job_title_and_employer() -> None:
    """Verifies generated resume and cover letter include target role and company name."""
    candidate = create_verified_candidate()
    job = create_test_job(title="Principal Infrastructure Lead", company="Cloudflare")

    # Generate tailored resume
    resume, text, report, model_name, p_ver = await resume_agent.generate_tailored_resume(candidate, job)
    assert resume.target_title == "Principal Infrastructure Lead"
    assert resume.target_company == "Cloudflare"
    assert "Cloudflare" in text
    assert "Principal Infrastructure Lead" in text
    assert report.is_clean is True

    # Generate tailored cover letter
    from app.services.documents.cover_letter_agent import cover_letter_agent
    letter, l_text, l_report, l_model, l_p_ver = await cover_letter_agent.generate_tailored_cover_letter(candidate, job)
    assert letter.target_company == "Cloudflare"
    assert letter.target_title == "Principal Infrastructure Lead"
    assert "Cloudflare" in l_text
    assert "Principal Infrastructure Lead" in l_text
    assert l_report.is_clean is True


def test_docx_and_pdf_files_render_and_open_successfully() -> None:
    """Verifies rendered DOCX and text-selectable PDF open cleanly and parse without corruption."""
    candidate = create_verified_candidate()
    clean_resume = StructuredResume(
        full_name="Alex Morgan",
        email="alex.morgan@test.com",
        target_title="Staff Backend Engineer",
        target_company="Datadog",
        professional_summary="Engineer with verified expertise in Python microservices.",
        highlighted_skills=["python", "postgresql", "docker"],
        experience=[
            ResumeExperienceItem(
                company="Stripe",
                title="Software Engineer",
                start_date="2021",
                end_date="2023",
                bullets=["Scaled payment architecture."],
            )
        ],
        education=[
            ResumeEducationItem(
                institution="University of Texas",
                degree="Bachelor of Science",
                field_of_study="Computer Science",
            )
        ],
    )

    # 1. Render DOCX
    docx_bytes = docx_renderer.render_resume(clean_resume, template_id="modern")
    assert isinstance(docx_bytes, bytes)
    assert len(docx_bytes) > 1000

    # Verify DOCX opens with python-docx
    doc_file = DocxReader(io.BytesIO(docx_bytes))
    full_doc_text = " ".join([p.text for p in doc_file.paragraphs])
    assert "Alex Morgan" in full_doc_text
    assert "Datadog" in full_doc_text
    assert "Stripe" in full_doc_text

    # 2. Render PDF
    pdf_bytes = pdf_renderer.render_resume(clean_resume, template_id="modern")
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000

    # Verify PDF text is selectable and headings are readable
    pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(pdf_reader.pages) >= 1
    extracted_pdf_text = pdf_reader.pages[0].extract_text()
    assert "Alex Morgan" in extracted_pdf_text
    assert "Datadog" in extracted_pdf_text
    assert "PROFESSIONAL EXPERIENCE" in extracted_pdf_text
    assert "Stripe" in extracted_pdf_text


def test_missing_ai_credentials_produce_clear_configuration_error() -> None:
    """Verifies that if live LLM is requested without credentials, a clear error is raised."""
    candidate = create_verified_candidate()
    job = create_test_job()

    with pytest.raises(MissingAIConfigurationError) as exc_info:
        # Force require_live_llm=True with placeholder keys
        import asyncio
        asyncio.run(
            resume_agent.generate_tailored_resume(candidate, job, require_live_llm=True)
        )

    assert "credentials are not configured" in str(exc_info.value).lower()


# -----------------------------------------------------------------------------
# Integration Tests: Endpoints, Versions, Immutability & Cross-User Security
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_document_generation_and_version_immutability(
    async_client: AsyncClient, auth_headers: dict
) -> None:
    """Verifies document generation, editing, and version history immutability."""
    import uuid
    db_gen = get_db()
    db = await anext(db_gen)

    unique_id = uuid.uuid4().hex[:8]
    test_job = JobPosting(
        source="greenhouse",
        source_id=f"test-doc-job-{unique_id}",
        canonical_url=f"https://example.com/job/{unique_id}",
        title="Senior Platform Engineer",
        company=f"TechCorp-{unique_id}",
        description="Requirements: Python, Docker, PostgreSQL.",
        location="Remote",
        work_mode="remote",
        employment_type="full_time",
    )
    db.add(test_job)
    await db.commit()
    await db.refresh(test_job)

    job_id = test_job.id

    # 1. Generate Resume via API
    gen_resp = await async_client.post(
        "/api/v1/documents/generate",
        json={
            "job_id": job_id,
            "doc_type": "resume",
            "template_id": "modern",
        },
        headers=auth_headers,
    )
    assert gen_resp.status_code == 201
    doc_data = gen_resp.json()
    doc_id = doc_data["id"]
    assert doc_data["title"] is not None
    assert doc_data["latest_version"]["version_number"] == 1
    v1_id = doc_data["latest_version"]["id"]

    # 2. Edit document content -> creates Version 2 without modifying Version 1
    structured = doc_data["latest_version"]["structured_data"]
    structured["professional_summary"] = "Updated summary specifically revised by candidate."

    update_resp = await async_client.put(
        f"/api/v1/documents/{doc_id}/versions",
        json={
            "structured_data": structured,
            "change_summary": "Revised executive summary",
            "is_approved": True,
        },
        headers=auth_headers,
    )
    assert update_resp.status_code == 201
    v2_data = update_resp.json()
    assert v2_data["version_number"] == 2
    assert v2_data["is_approved"] is True
    assert v2_data["id"] != v1_id

    # 3. Retrieve version history
    history_resp = await async_client.get(
        f"/api/v1/documents/{doc_id}/versions",
        headers=auth_headers,
    )
    assert history_resp.status_code == 200
    versions = history_resp.json()
    assert len(versions) == 2
    # Verify version 1 was NOT silently overwritten
    v1_found = next(v for v in versions if v["version_number"] == 1)
    v2_found = next(v for v in versions if v["version_number"] == 2)
    assert v1_found["structured_data"]["professional_summary"] != v2_found["structured_data"]["professional_summary"]

    # 4. Download DOCX and PDF
    download_pdf = await async_client.get(
        f"/api/v1/documents/{doc_id}/download?format=pdf",
        headers=auth_headers,
    )
    assert download_pdf.status_code == 200
    assert download_pdf.headers["content-type"] == "application/pdf"
    assert len(download_pdf.content) > 500

    download_docx = await async_client.get(
        f"/api/v1/documents/{doc_id}/download?format=docx",
        headers=auth_headers,
    )
    assert download_docx.status_code == 200
    assert "wordprocessingml" in download_docx.headers["content-type"]
    assert len(download_docx.content) > 500


@pytest.mark.asyncio
async def test_cross_user_document_access_denied(
    async_client: AsyncClient, auth_headers: dict
) -> None:
    """Verifies that users cannot view, edit, or download another user's documents."""
    import uuid
    db_gen = get_db()
    db = await anext(db_gen)

    unique_id = uuid.uuid4().hex[:8]
    test_job = JobPosting(
        source="greenhouse",
        source_id=f"test-doc-job-{unique_id}",
        canonical_url=f"https://example.com/job/{unique_id}",
        title="SecOps Engineer",
        company="SecureCloud",
        description="Requirements: Python, Security.",
        location="Remote",
        work_mode="remote",
        employment_type="full_time",
    )
    db.add(test_job)
    await db.commit()
    await db.refresh(test_job)

    # Register User B with unique email
    b_email = f"userb_{unique_id}@example.com"
    b_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": b_email, "password": "SecurePassword123!", "full_name": "User B"},
    )
    assert b_resp.status_code in (200, 201)
    user_b_token = b_resp.json()["token"]
    user_b_headers = {"Authorization": f"Bearer {user_b_token}"}

    # User A generates document
    gen_resp = await async_client.post(
        "/api/v1/documents/generate",
        json={"job_id": test_job.id, "doc_type": "cover_letter"},
        headers=auth_headers,
    )
    assert gen_resp.status_code == 201
    user_a_doc_id = gen_resp.json()["id"]

    # User B attempts to access User A's document -> 403 Forbidden
    b_get = await async_client.get(f"/api/v1/documents/{user_a_doc_id}", headers=user_b_headers)
    assert b_get.status_code == 403

    # User B attempts to edit User A's document -> 403 Forbidden
    b_put = await async_client.put(
        f"/api/v1/documents/{user_a_doc_id}/versions",
        json={"structured_data": {}},
        headers=user_b_headers,
    )
    assert b_put.status_code == 403

    # User B attempts to download User A's document -> 403 Forbidden
    b_dl = await async_client.get(
        f"/api/v1/documents/{user_a_doc_id}/download?format=pdf",
        headers=user_b_headers,
    )
    assert b_dl.status_code == 403
