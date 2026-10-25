"""Integration tests for job matching endpoints, ranking, filtering, and invalidation."""

from datetime import datetime, timezone
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select

from app.core.database import get_db
from app.main import app
from app.models.entities import JobMatch, JobPosting, Profile, Skill, User
from app.schemas.job import NormalizedJob
from app.services.job_service import JobService
from app.services.matching_service import MatchingService


@pytest.fixture
async def auth_headers(async_client: AsyncClient):
    """Registers and authenticates candidate user for matching tests."""
    reg_payload = {
        "email": "candidate.match@example.com",
        "password": "Password123!Secure",
        "full_name": "Match Candidate",
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
async def test_get_scoring_weights_endpoint(async_client: AsyncClient) -> None:
    """Verifies GET /api/v1/matches/weights returns weights summing to 100%."""
    resp = await async_client.get("/api/v1/matches/weights")
    assert resp.status_code == 200
    data = resp.json()
    weights = data["weights"]
    assert weights["required_skills"] == 0.35
    assert weights["role_relevance"] == 0.25
    assert sum(weights.values()) == 1.0


@pytest.mark.asyncio
async def test_matching_flow_ranking_and_filters(async_client: AsyncClient, auth_headers: dict) -> None:
    """Verifies end-to-end matching evaluation, ranking, filtering by min_score, and sorting."""
    # 1. Update candidate profile and skills
    await async_client.put(
        "/api/v1/profile/me",
        json={
            "target_job_titles": ["Full Stack Engineer", "Python Developer"],
            "remote_preference": "remote",
            "work_authorization_status": "authorized_without_sponsorship",
            "location": "Remote, USA",
        },
        headers=auth_headers,
    )
    # Add skills
    await async_client.post(
        "/api/v1/profile/skills",
        json={"name": "Python", "proficiency_level": "expert", "years_experience": 5.0},
        headers=auth_headers,
    )
    await async_client.post(
        "/api/v1/profile/skills",
        json={"name": "FastAPI", "proficiency_level": "advanced", "years_experience": 3.0},
        headers=auth_headers,
    )

    # 2. Insert two jobs in DB (High match and Low match)
    db_gen = get_db()
    db = await anext(db_gen)

    now = datetime.now(timezone.utc)
    # High match job
    job_high = await JobService.upsert_normalized_job(
        db,
        NormalizedJob(
            source="greenhouse",
            source_id="gh-match-high-1",
            canonical_url="https://example.com/jobs/match-high",
            title="Senior Python Developer",
            company="Python Cloud Inc",
            description="Requirements: Strong experience in Python and FastAPI. Remote opportunity.",
            work_mode="remote",
            retrieved_at=now,
        ),
    )

    # Low match job (requires Java and Onsite)
    job_low = await JobService.upsert_normalized_job(
        db,
        NormalizedJob(
            source="greenhouse",
            source_id="gh-match-low-1",
            canonical_url="https://example.com/jobs/match-low",
            title="Embedded C++ Engineer",
            company="Hardware Corp",
            description="Requirements: 8+ years embedded C++ and assembly. Onsite required.",
            work_mode="onsite",
            retrieved_at=now,
        ),
    )

    # 3. Request ranked matches
    resp = await async_client.get("/api/v1/matches?sort_by=score_desc", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    items = data["items"]
    assert len(items) >= 2

    # High match job must rank first when sorted by score_desc
    assert items[0]["total_score"] >= items[1]["total_score"]
    assert items[0]["job"]["id"] == job_high.id
    assert items[0]["total_score"] > 60.0

    # 4. Filter by min_score
    resp_filtered = await async_client.get("/api/v1/matches?min_score=60", headers=auth_headers)
    assert resp_filtered.status_code == 200
    filtered_items = resp_filtered.json()["items"]
    assert all(m["total_score"] >= 60.0 for m in filtered_items)

    # 5. Get detailed single match
    detail_resp = await async_client.get(f"/api/v1/matches/{job_high.id}", headers=auth_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["job_id"] == job_high.id
    assert "explanation" in detail
    assert "component_scores" in detail
    assert detail["component_scores"]["required_skills"] > 0


@pytest.mark.asyncio
async def test_profile_update_invalidates_stale_matches(async_client: AsyncClient, auth_headers: dict) -> None:
    """Verifies that updating profile attributes marks existing matches as stale."""
    # Ensure at least 1 match exists
    list_resp = await async_client.get("/api/v1/matches", headers=auth_headers)
    assert list_resp.status_code == 200

    # Update matching preferences
    pref_resp = await async_client.put(
        "/api/v1/matches/preferences",
        json={"target_job_titles": ["Staff Architect"], "remote_preference": "onsite"},
        headers=auth_headers,
    )
    assert pref_resp.status_code == 200

    # Verify existing match records in database are flagged is_stale == True
    db_gen = get_db()
    db = await anext(db_gen)

    # Check database
    me_resp = await async_client.get("/api/v1/auth/me", headers=auth_headers)
    user_id = me_resp.json()["id"]

    stmt = select(JobMatch).where(JobMatch.user_id == user_id)
    res = await db.execute(stmt)
    matches = list(res.scalars().all())
    if matches:
        assert all(m.is_stale is True for m in matches)

    # Recalculate clears stale flag
    recalc_resp = await async_client.post("/api/v1/matches/recalculate", headers=auth_headers)
    assert recalc_resp.status_code == 200

    db.expire_all()
    stmt2 = select(JobMatch).where(JobMatch.user_id == user_id)
    res2 = await db.execute(stmt2)
    recalculated = list(res2.scalars().all())
    assert len(recalculated) > 0
    assert all(m.is_stale is False for m in recalculated)
    await db.close()
