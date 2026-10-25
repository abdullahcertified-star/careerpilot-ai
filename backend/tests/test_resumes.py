import io
import uuid
import pytest
from docx import Document
from httpx import AsyncClient
from pypdf import PdfWriter


def make_test_pdf_bytes(text: str) -> bytes:
    """Create a valid in-memory PDF document with extractable text."""
    stream = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET"
    stream_len = len(stream)
    content = f"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length {stream_len} >> stream
{stream}
endstream endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000350 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
420
%%EOF"""
    return content.encode("latin1")


def make_test_docx_bytes(paragraphs: list[str]) -> bytes:
    """Create a valid in-memory DOCX document."""
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


async def create_candidate(async_client: AsyncClient, name: str = "Candidate") -> tuple[str, dict]:
    """Helper to create candidate and return (token, auth_headers)."""
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": name},
    )
    token = resp.json()["token"]
    return token, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_valid_pdf_upload_and_parse(async_client: AsyncClient) -> None:
    """Valid PDF resume uploads, parses successfully, and extracts facts with evidence snippets."""
    _, headers = await create_candidate(async_client, "Alex Morgan")
    pdf_content = make_test_pdf_bytes(
        "Alex Morgan - Senior AI Engineer. Skills: Python, FastAPI, Docker, PostgreSQL. "
        "Senior Software Engineer, TechCorp, 2022 to Present. "
        "Bachelor of Science in Computer Science, Tech University. "
        "AWS Certified Solutions Architect."
    )

    # 1. Upload
    files = {"file": ("alex_resume.pdf", pdf_content, "application/pdf")}
    upload_resp = await async_client.post("/api/v1/resumes/upload", headers=headers, files=files)
    assert upload_resp.status_code == 201
    resume_id = upload_resp.json()["id"]

    # 2. Parse
    parse_resp = await async_client.post(f"/api/v1/resumes/{resume_id}/parse", headers=headers)
    assert parse_resp.status_code == 200
    data = parse_resp.json()
    assert data["status"] == "pending_review"
    assert data["page_count"] >= 1

    extracted = data["extracted_data"]
    # Verify grounded skills
    skill_names = [s["name"] for s in extracted["skills"]]
    assert "Python" in skill_names
    assert "FastAPI" in skill_names

    # Verify evidence source presence
    first_skill = extracted["skills"][0]
    assert "evidence" in first_skill
    assert first_skill["evidence"]["text_snippet"] != ""
    assert first_skill["evidence"]["page_number"] >= 1


@pytest.mark.asyncio
async def test_valid_docx_upload_and_parse(async_client: AsyncClient) -> None:
    """Valid DOCX resume uploads and parses successfully."""
    _, headers = await create_candidate(async_client, "Jordan Lee")
    docx_content = make_test_docx_bytes([
        "Jordan Lee - Full Stack Developer",
        "Technical Skills: TypeScript, React, Next.js, Node.js",
        "Staff Software Architect, CloudSystems, 2020 to Present",
        "Master of Science in Software Engineering, State University",
    ])

    files = {"file": ("jordan_resume.docx", docx_content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    upload_resp = await async_client.post("/api/v1/resumes/upload", headers=headers, files=files)
    assert upload_resp.status_code == 201
    resume_id = upload_resp.json()["id"]

    parse_resp = await async_client.post(f"/api/v1/resumes/{resume_id}/parse", headers=headers)
    assert parse_resp.status_code == 200
    extracted = parse_resp.json()["extracted_data"]
    skill_names = [s["name"] for s in extracted["skills"]]
    assert "TypeScript" in skill_names or "React" in skill_names


@pytest.mark.asyncio
async def test_empty_and_oversized_file_rejected(async_client: AsyncClient) -> None:
    """Empty and oversized files are rejected with appropriate error codes."""
    _, headers = await create_candidate(async_client)

    # Empty file
    files_empty = {"file": ("empty.pdf", b"", "application/pdf")}
    resp_empty = await async_client.post("/api/v1/resumes/upload", headers=headers, files=files_empty)
    assert resp_empty.status_code == 400
    assert "empty" in resp_empty.json()["detail"].lower()

    # Oversized file (> 10MB)
    oversized_bytes = b"%PDF" + (b"0" * (10 * 1024 * 1024 + 100))
    files_big = {"file": ("big.pdf", oversized_bytes, "application/pdf")}
    resp_big = await async_client.post("/api/v1/resumes/upload", headers=headers, files=files_big)
    assert resp_big.status_code == 413


@pytest.mark.asyncio
async def test_unsupported_extension_and_mime_spoofing(async_client: AsyncClient) -> None:
    """Unsupported extensions and spoofed magic bytes are rejected."""
    _, headers = await create_candidate(async_client)

    # Unsupported extension
    files_exe = {"file": ("malicious.exe", b"MZ\x90\x00\x03", "application/octet-stream")}
    resp_exe = await async_client.post("/api/v1/resumes/upload", headers=headers, files=files_exe)
    assert resp_exe.status_code == 415

    # MIME spoofing: EXE payload disguised with .pdf filename
    fake_pdf = {"file": ("exploit.pdf", b"MZ\x90\x00\x03\x00\x00\x00\x04", "application/pdf")}
    resp_spoof = await async_client.post("/api/v1/resumes/upload", headers=headers, files=fake_pdf)
    assert resp_spoof.status_code == 400
    assert "spoofing detected" in resp_spoof.json()["detail"].lower()

    # MIME spoofing: Non-zip text payload disguised as .docx
    fake_docx = {"file": ("exploit.docx", b"Plain text disguised as docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    resp_spoof_docx = await async_client.post("/api/v1/resumes/upload", headers=headers, files=fake_docx)
    assert resp_spoof_docx.status_code == 400
    assert "spoofing detected" in resp_spoof_docx.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cross_user_downloads_and_modifications_denied(async_client: AsyncClient) -> None:
    """User A cannot download, delete, or parse User B's resume."""
    _, headers_a = await create_candidate(async_client, "User A")
    _, headers_b = await create_candidate(async_client, "User B")

    # User A uploads resume
    pdf_content = make_test_pdf_bytes("User A Resume Content. Skills: Python, Docker, Linux.")
    files = {"file": ("user_a_cv.pdf", pdf_content, "application/pdf")}
    upload_resp = await async_client.post("/api/v1/resumes/upload", headers=headers_a, files=files)
    resume_a_id = upload_resp.json()["id"]

    # User B attempts to download User A's resume -> 403 Forbidden
    download_resp = await async_client.get(f"/api/v1/resumes/{resume_a_id}/download", headers=headers_b)
    assert download_resp.status_code == 403
    assert "Access denied" in download_resp.json()["detail"]

    # User B attempts to parse User A's resume -> 403 Forbidden
    parse_resp = await async_client.post(f"/api/v1/resumes/{resume_a_id}/parse", headers=headers_b)
    assert parse_resp.status_code == 403

    # User B attempts to delete User A's resume -> 403 Forbidden
    del_resp = await async_client.delete(f"/api/v1/resumes/{resume_a_id}", headers=headers_b)
    assert del_resp.status_code == 403

    # User A can download own resume
    my_download = await async_client.get(f"/api/v1/resumes/{resume_a_id}/download", headers=headers_a)
    assert my_download.status_code == 200

    # User A deletes own resume
    my_delete = await async_client.delete(f"/api/v1/resumes/{resume_a_id}", headers=headers_a)
    assert my_delete.status_code == 200

    # Deleted resume cannot be downloaded anymore
    re_download = await async_client.get(f"/api/v1/resumes/{resume_a_id}/download", headers=headers_a)
    assert re_download.status_code == 404


@pytest.mark.asyncio
async def test_extracted_facts_staging_editing_and_confirmation(async_client: AsyncClient) -> None:
    """
    Extracted facts are staged separately from verified profile.
    They can be reviewed, edited, and explicitly confirmed into the verified profile.
    """
    _, headers = await create_candidate(async_client, "Taylor")

    # Upload and parse resume
    pdf_content = make_test_pdf_bytes("Taylor - Staff Engineer. Skills: Python, Redis, GraphQL. Senior Engineer at AcmeCorp.")
    files = {"file": ("taylor_cv.pdf", pdf_content, "application/pdf")}
    upload_resp = await async_client.post("/api/v1/resumes/upload", headers=headers, files=files)
    resume_id = upload_resp.json()["id"]

    await async_client.post(f"/api/v1/resumes/{resume_id}/parse", headers=headers)

    # 1. Check verified candidate profile BEFORE confirmation: must NOT contain new unconfirmed skills!
    pre_profile = await async_client.get("/api/v1/profile/me", headers=headers)
    assert pre_profile.status_code == 200
    pre_skills = [s["name"] for s in pre_profile.json()["skills"]]
    assert "Redis" not in pre_skills

    # 2. Get staged extraction
    extraction_resp = await async_client.get(f"/api/v1/resumes/{resume_id}/extraction", headers=headers)
    assert extraction_resp.status_code == 200
    extraction_data = extraction_resp.json()["extracted_data"]

    # 3. Candidate edits staged fact (e.g. adjusts headline and unconfirms a skill)
    extraction_data["headline"] = "Principal Distributed AI Architect"
    # Unconfirm one skill to test that unconfirmed claims are not merged
    for s in extraction_data["skills"]:
        if s["name"] == "GraphQL":
            s["is_confirmed"] = False

    # Save edit
    put_resp = await async_client.put(
        f"/api/v1/resumes/{resume_id}/extraction",
        headers=headers,
        json=extraction_data,
    )
    assert put_resp.status_code == 200

    # 4. Confirm extraction into verified profile
    confirm_resp = await async_client.post(
        f"/api/v1/resumes/{resume_id}/extraction/confirm",
        headers=headers,
        json={
            "data": extraction_data,
            "override_headline": True,
            "override_bio": True,
            "override_location": True,
        },
    )
    assert confirm_resp.status_code == 200
    assert "Extraction verified" in confirm_resp.json()["message"]

    # 5. Verify candidate profile NOW reflects confirmed items, but NOT the unconfirmed item!
    post_profile = await async_client.get("/api/v1/profile/me", headers=headers)
    assert post_profile.status_code == 200
    post_skills = [s["name"] for s in post_profile.json()["skills"]]
    assert "Python" in post_skills
    assert "Redis" in post_skills
    assert "GraphQL" not in post_skills  # Was unconfirmed, so never added!
    assert post_profile.json()["profile"]["headline"] == "Principal Distributed AI Architect"


@pytest.mark.asyncio
async def test_parsing_errors_do_not_corrupt_existing_profile(async_client: AsyncClient) -> None:
    """Parsing an empty or unparseable document raises clean error and preserves existing profile."""
    _, headers = await create_candidate(async_client, "Morgan")

    # Set initial headline
    await async_client.put(
        "/api/v1/profile/me",
        headers=headers,
        json={"headline": "Original Untouched Headline"},
    )

    # Attempt to upload PDF with minimal text (< 20 chars)
    short_pdf = make_test_pdf_bytes("Hi")
    files = {"file": ("short.pdf", short_pdf, "application/pdf")}
    upload_resp = await async_client.post("/api/v1/resumes/upload", headers=headers, files=files)
    resume_id = upload_resp.json()["id"]

    parse_resp = await async_client.post(f"/api/v1/resumes/{resume_id}/parse", headers=headers)
    assert parse_resp.status_code == 422
    assert "insufficient extractable text" in parse_resp.json()["detail"].lower()

    # Verify original profile remains completely intact
    profile_check = await async_client.get("/api/v1/profile/me", headers=headers)
    assert profile_check.status_code == 200
    assert profile_check.json()["profile"]["headline"] == "Original Untouched Headline"
