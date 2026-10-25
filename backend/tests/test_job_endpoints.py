"""Integration tests for job search, deduplication, URL import, and saved jobs."""

from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select

from app.core.database import get_db
from app.main import app
from app.models.entities import JobPosting, SavedJob, User
from app.schemas.job import NormalizedJob
from app.services.job_service import JobService


@pytest.fixture
async def auth_headers(async_client: AsyncClient):
    """Registers and authenticates a test user, returning auth headers."""
    reg_payload = {
        "email": "candidate.phase3@example.com",
        "password": "Password123!Secure",
        "full_name": "Phase Three Candidate",
    }
    resp = await async_client.post("/api/v1/auth/register", json=reg_payload)
    if resp.status_code != 201:
        # Already registered, log in
        login_resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": reg_payload["email"], "password": reg_payload["password"]},
        )
        token = login_resp.json()["token"]
    else:
        token = resp.json()["token"]

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def auth_headers_user2(async_client: AsyncClient):
    """Registers and authenticates a second test user for cross-user tests."""
    reg_payload = {
        "email": "user2.phase3@example.com",
        "password": "Password123!Secure",
        "full_name": "Second User",
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


@pytest.mark.asyncio
async def test_list_providers_endpoint(async_client: AsyncClient) -> None:
    """Verifies GET /api/v1/jobs/providers returns capabilities with clear status."""
    resp = await async_client.get("/api/v1/jobs/providers")
    assert resp.status_code == 200
    providers = resp.json()
    provider_ids = [p["provider_id"] for p in providers]
    assert "greenhouse" in provider_ids
    assert "linkedin" in provider_ids
    assert "indeed" in provider_ids
    assert "manual_import" in provider_ids

    # Verify link-first flags
    linkedin = next(p for p in providers if p["provider_id"] == "linkedin")
    assert linkedin["integration_status"] == "link_first"
    assert linkedin["link_first_only"] is True


@pytest.mark.asyncio
async def test_job_deduplication_by_source_and_canonical_url(async_client: AsyncClient, auth_headers: dict) -> None:
    """Verifies that inserting identical jobs or URLs with tracking params updates rather than duplicates."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    db_gen = get_db()
    db = await anext(db_gen)

    # 1. Insert original job
    job1 = NormalizedJob(
        source="greenhouse",
        source_id="gh-dup-test-1",
        canonical_url="https://boards.greenhouse.io/acme/jobs/100?utm_source=twitter&utm_medium=social",
        title="Initial Title",
        company="Acme Corp",
        description="Initial Description",
        work_mode="remote",
        retrieved_at=now,
    )
    saved_job1 = await JobService.upsert_normalized_job(db, job1)
    orig_id = saved_job1.id

    # 2. Insert with same source and source_id but updated title
    job2 = NormalizedJob(
        source="greenhouse",
        source_id="gh-dup-test-1",
        canonical_url="https://boards.greenhouse.io/acme/jobs/100?ref=newsletter",
        title="Updated Title",
        company="Acme Corp",
        description="Updated Description",
        work_mode="remote",
        retrieved_at=now,
    )
    saved_job2 = await JobService.upsert_normalized_job(db, job2)
    assert saved_job2.id == orig_id
    assert saved_job2.title == "Updated Title"

    # 3. Insert with different source_id but identical canonical URL (ignoring tracking query params)
    job3 = NormalizedJob(
        source="partner_feed",
        source_id="partner-dup-99",
        canonical_url="https://boards.greenhouse.io/acme/jobs/100?utm_campaign=spring2026",
        title="Partner Feed Title",
        company="Acme Corp",
        description="Partner Description",
        work_mode="remote",
        retrieved_at=now,
    )
    saved_job3 = await JobService.upsert_normalized_job(db, job3)
    assert saved_job3.id == orig_id  # Deduplicated on canonical URL


@pytest.mark.asyncio
async def test_import_job_url_endpoint_rejects_ssrf(async_client: AsyncClient, auth_headers: dict) -> None:
    """Verifies POST /api/v1/jobs/import-url returns 400 for prohibited loopback and private IPs."""
    prohibited_payloads = [
        {"url": "http://127.0.0.1:8000/api/v1/profile"},
        {"url": "http://localhost:3000/secret"},
        {"url": "http://169.254.169.254/latest/meta-data/"},
        {"url": "http://10.0.0.1/admin"},
        {"url": "file:///etc/passwd"},
    ]

    for payload in prohibited_payloads:
        resp = await async_client.post("/api/v1/jobs/import-url", json=payload, headers=auth_headers)
        assert resp.status_code == 400
        assert "security" in resp.json()["detail"].lower() or "prohibited" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_import_job_url_success(async_client: AsyncClient, auth_headers: dict) -> None:
    """Verifies POST /api/v1/jobs/import-url successfully parses and saves valid job page."""
    mock_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta property="og:title" content="Staff Security Engineer at CloudGuard" />
        <meta property="og:site_name" content="CloudGuard Security" />
        <meta property="og:description" content="Lead application security architecture and vulnerability management." />
        <link rel="canonical" href="https://cloudguard.example.com/careers/staff-security-engineer" />
    </head>
    <body>
        <p>Remote position in North America.</p>
    </body>
    </html>
    """

    with patch(
        "app.integrations.job_providers.manual_import.safe_fetch_url",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = (
            "https://cloudguard.example.com/careers/staff-security-engineer",
            mock_html,
            {"content-type": "text/html"},
        )

        resp = await async_client.post(
            "/api/v1/jobs/import-url",
            json={"url": "https://cloudguard.example.com/careers/staff-security-engineer"},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "Staff Security Engineer" in data["title"]
        assert "CloudGuard" in data["company"]
        assert data["source"] == "manual_import"
        assert data["work_mode"] == "remote"
        assert data["id"] > 0


@pytest.mark.asyncio
async def test_saved_jobs_lifecycle_and_ownership(
    async_client: AsyncClient, auth_headers: dict, auth_headers_user2: dict
) -> None:
    """Verifies bookmarking, listing, updating notes, ownership checks, and unsaving jobs."""
    # 1. Create a job directly in database
    from datetime import datetime, timezone
    db_gen = get_db()
    db = await anext(db_gen)

    job = await JobService.upsert_normalized_job(
        db,
        NormalizedJob(
            source="greenhouse",
            source_id="gh-saved-flow-1",
            canonical_url="https://boards.greenhouse.io/acme/jobs/saved-flow-1",
            title="Senior Platform Architect",
            company="Acme Cloud",
            description="Lead multi-cloud Kubernetes infrastructure.",
            work_mode="remote",
            retrieved_at=datetime.now(timezone.utc),
        ),
    )
    job_id = job.id

    # 2. User 1 saves the job
    save_resp = await async_client.post(
        f"/api/v1/jobs/{job_id}/save",
        json={"notes": "High priority: referral from Alice", "status": "saved"},
        headers=auth_headers,
    )
    assert save_resp.status_code == 200
    saved_data = save_resp.json()
    saved_id = saved_data["id"]
    assert saved_data["status"] == "saved"
    assert saved_data["notes"] == "High priority: referral from Alice"
    assert saved_data["job"]["title"] == "Senior Platform Architect"

    # 3. User 1 lists saved jobs
    list_resp = await async_client.get("/api/v1/jobs/saved", headers=auth_headers)
    assert list_resp.status_code == 200
    user1_saved = list_resp.json()
    assert any(s["id"] == saved_id for s in user1_saved)

    # 4. User 1 updates status and notes
    patch_resp = await async_client.patch(
        f"/api/v1/jobs/saved/{saved_id}",
        json={"status": "applied", "notes": "Applied on 2026-10-11 via company portal."},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "applied"
    assert "company portal" in patch_resp.json()["notes"]

    # 5. Cross-user security check: User 2 tries to modify User 1's saved job -> rejected 404
    cross_patch = await async_client.patch(
        f"/api/v1/jobs/saved/{saved_id}",
        json={"notes": "Malicious override attempt"},
        headers=auth_headers_user2,
    )
    assert cross_patch.status_code == 404

    # 6. User 2 lists their own saved jobs -> should be empty
    user2_list = await async_client.get("/api/v1/jobs/saved", headers=auth_headers_user2)
    assert user2_list.status_code == 200
    assert not any(s["id"] == saved_id for s in user2_list.json())

    # 7. User 1 unsaves the job
    unsave_resp = await async_client.delete(f"/api/v1/jobs/{job_id}/save", headers=auth_headers)
    assert unsave_resp.status_code == 200

    # 8. Verify it is no longer in User 1's saved list
    final_list = await async_client.get("/api/v1/jobs/saved", headers=auth_headers)
    assert final_list.status_code == 200
    assert not any(s["id"] == saved_id for s in final_list.json())
